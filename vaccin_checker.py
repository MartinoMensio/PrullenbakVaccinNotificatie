from math import sqrt, ceil
import time
import pickle
import os, sys
import string
import random
import smtplib, ssl
import datetime
import re
import sqlite3 as sqlite
import requests
import redis
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup


def timestamp():
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return stamp


def write_log(message, also_print=True, is_error = False):
    '''Write a message to the debug log'''
    with open('logs/checker_debug.log','a') as debug_f:
        debug_f.write(f"[{timestamp()}] {message}\n")
    if is_error == True:
        with open('logs/checker_error.log','a') as debug_f:
            debug_f.write(f"[{timestamp()}] {message}\n")
    if also_print == True:
        print(message)


def log_var(var):
    rand_id = "".join(random.choices(string.ascii_uppercase, k=16))
    fname = f"logs/var_{rand_id}.p"
    write_log(f"Var written to {fname}", is_error = True)
    pickle.dump(var, open(fname, "wb"))


def parse_site():
    postcode_regex = "[\d]{4}( |)[A-Za-z]{2}( |)"
    now_avail = {}
    
    r = requests.get("https://www.prullenbakvaccin.nl/")
    
    if test_run == True:
        r = pickle.load(open("debug/test_pos_1.p", "rb"))
    
    if r.status_code != 200:
        write_log(f"Parser status code was {r.status_code}", is_error=True)
        log_var(r)
        return {}
    soup = BeautifulSoup(r.content, "html.parser")
    soup = soup.find("div", attrs={"id": "locations-container"})
    if not soup:
        write_log("No available locations")
        return {} # No available locations
    soup = soup.find_all("div", attrs={"class": "card mb-2"})
    if not soup:
        write_log("Available location but no html card found", is_error=True)
        log_var(r)
        return {}
    
    for elem in soup: # Loop over all doctors now available
        locatie_id = elem.find("h5")["id"]
        if not locatie_id:
            write_log("locatie_id could not be found in html card", is_error=True)
            log_var(elem)
            return {}
        locatie_text = str(elem.find("p", attrs={"class": "card-text"}))
        match = re.search(postcode_regex, locatie_text)
        if not match:
            write_log("postcode could not be found in html card", is_error=True)
            log_var(locatie_text)
            return {}
        postcode = match.group(0)
        postcode = postcode.replace(" ", "").upper()
        now_avail[locatie_id] = {"postcode": postcode, "html_card": elem}
        write_log(f"{locatie_id} is available at {postcode}")
    return now_avail


def nearby_entries(coords):
    lat = coords["lat"]; long = coords["long"]
    lat_range = 0.18; long_range = 0.28 # +-20km
    low_lat = lat - lat_range; high_lat = lat + lat_range
    low_long = long - long_range; high_long = long + long_range
    try:
        conn = sqlite.connect(f"file:{db_file}?mode=ro", uri=True)
    except Exception as E:
        write_log(f"Exception while trying to connect to db: {E}", is_error=True)
        return []
    try:
        cur = conn.cursor()
        cur.execute("""
        SELECT email, token, max_dist, lat, long FROM users
        WHERE lat BETWEEN ? AND ? AND long BETWEEN ? AND ?;
        """, (low_lat, high_lat, low_long, high_long))
        
        entries = cur.fetchall()
    except Exception as E:
        write_log(f"Exception while trying to query db: {E}", is_error=True)
        conn.close()
        return []
    conn.close()
    return entries   


def postcode_coordinate(postcode):
    for i in range(3): # Retry 2 times
        api = "https://bwnr.nl/postcode.php"
        params = {"ak": bwnr_API_KEY,
                  "pc": postcode,
                  "ac": "pc2straat",
                  "tg": "data"}
        start_time = datetime.datetime.now()
        resp = requests.get(api, params=params)
        r_time = int((datetime.datetime.now() - start_time).total_seconds() * 1000) # Time the API call
        write_log(f"postcode API call took {r_time}ms")
        resp = resp.content.decode().split(";")
        if len(resp) == 4:
            break
        elif i == 2:
            write_log("postcode API call failed after 2 retries", is_error=True)
            return None
        else:
            write_log(f"postcode API call for {postcode} failed with: {resp}", is_error=True)
            time.sleep(1)
          
    lat = round(float(resp[2]), 3)
    long = round(float(resp[3]), 3)
    return {"lat": lat, "long": long}


def filter_distance(entries, coords):
    return_entries = []
    for entry in entries:
        lat_dist = abs(entry[3] - coords["lat"]) * 110 * 1000 # Calculatee lat dist in m
        long_dist = abs(entry[4] - coords["long"]) * 70 * 1000 # Calcualte long dist in m
        dist = sqrt(lat_dist**2 + long_dist**2)
        if dist < entry[2]:
            entry = list(entry)
            entry.append(dist)
            return_entries.append(entry)
    return return_entries


def connect_smtp(mail_service, context):
    mail_conf = MS[mail_service]
    try:
        server = smtplib.SMTP(mail_conf["smtp"], mail_conf["port"])
        server.starttls(context=context)
        server.login(mail_conf["user"], mail_conf["pass"])
        return server
    except Exception as E:
        write_log(f"Exception during SMTP connect for {mail_service}: {E}", is_error=True)
        return None


def login_mail_servers(context, is_test = False):
    servers = {}
    for mail_service in MS:
        for i in range(3): # retry 2 times
            server = connect_smtp(mail_service, context)
            if server:
                write_log(f"Log in for {mail_service} succeeded.")
                if is_test == True:
                    server.quit()
                else:
                    servers[mail_service] = server
                break # stop retry
        if not server:
            write_log(f"Login in failed for {mail_service} after 2 retries", is_error=True)
            sys.exit(f"Login for {mail_service} failed!")
    return servers


def recommend_mail_service(mail_service):
    if test_run == True:
        return test_mail_service
    
    if mail_service == "sendinblue":
        if len(R.keys(f"sendinblue:24h:*")) > 280 or len(R.keys(f"sendinblue:1h:*")) > 90:
            write_log("sendinblue is near limit switching")
            mail_service = "mailjet"
        else: # When not over limit
            return mail_service

    if mail_service == "mailjet":
        if len(R.keys(f"mailjet:24h:*")) > 180 or len(R.keys(f"mailjet:1h:*")) > 90:
            write_log("mailjet is near limit switching")
            mail_service = "aws"
        else: # When not over limit
            return mail_service
    
    if mail_service == "aws":
        return mail_service


def format_message(entry, loc):
    to_address = entry[0]
    token = entry[1]
    distance = ceil(entry[5] / 1000)
    
    message = MIMEMultipart()
    message["Subject"] = f"Vaccin nu beschikbaar op prullenbakvaccin.nl op {distance}km afstand"
    message["From"] = from_address
    message["To"] = to_address
    
    body = f"""
    <h2>Er is nu een vaccin beschikbaar op <a href=https://www.prullenbakvaccin.nl/>prullenbakvaccin.nl</a></h2>
    <p>De locatie blijft maar <b>10 minuten</b> zichtbaar op de website. Zorg dat u de informatie op prullenbakvaccin.nl goed heeft doorgelezen. <br>
    <b>Als u naar de locatie gaat vergeet dan niet:</b>
    <ul>
    <li>Geldig paspoort, ID-bewijs of rijbewijs</li>
    <li>Het uitprinten en meenemen van de <a href="https://www.nhg.org/sites/default/files/content/nhg_org/uploads/final_gezondheidsverklaring_03_2021_web.pdf" target="_blank">'gezondheidscheck'</a>.</li>
    <li>Het dragen van een mondkapje is verplicht.</li>
    </ul>
    Hieronder staat een kopie van de praktijk informatie die op prullenbakvaccin.nl zichtbaar is:
    </p>
    <blockquote>
    {loc["html_card"]}
    </blockquote>
    <p>Wilt u geen e-mails meer ontvangen? Klik dan <a href=https://www.wilke.sh/PrullenbakVaccin/unsub?email={to_address}&token={token}>hier.</a> <br>
     U kunt <b>niet</b> op deze e-mail reageren. Contact en feedback kan via <a href=mailto:dev.yanowilke@gmail.com>dev.yanowilke@gmail.com</a></p>
    """
    message.attach(MIMEText(body, "html"))
    return message


def update_redis(mail_service):
    if mail_service == "aws":
        return
    rand_id = random.randint(1, 10000000)
    R.set(f"{mail_service}:24h:{rand_id}", 1, ex = 90000) # expire after 25 hours
    R.set(f"{mail_service}:1h:{rand_id}", 1, ex = 3900) # expire after 1h05m


def notify_users(loc, context):
    servers = login_mail_servers(context)
    mail_service = "sendinblue"
    write_log(f"{len(loc['users'])} users to notify for {loc['id']}")
    if len(loc["users"]) > max_per_loc: # When there are too many people select n random people to notify
        loc["users"] = random.sample(loc["users"], max_per_loc)
        write_log(f"downsampling users to {max_per_loc}")
    for entry in loc["users"]:
        mail_service = recommend_mail_service(mail_service)
        message = format_message(entry, loc)
        try:
            start_time = datetime.datetime.now() # Log start time
            servers[mail_service].sendmail(from_address, entry[0], message.as_string())
            update_redis(mail_service)
            loop_time = int((datetime.datetime.now() - start_time).total_seconds()) # Time how long loop took
            remaining = MS[mail_service]["sleep"] - loop_time # How long to wait for consistant loop time
            if remaining > 0:
                time.sleep(remaining) #variable sleep time per mail service
        except Exception as E:
            write_log(f"Exception while sending mail, update redis: {E}", is_error=True)
    write_log("emails for location send")


def find_nearby_email(new_locs):
    return_locs = []
    for loc in new_locs:
        coords = postcode_coordinate(loc["postcode"])
        if not coords:
            continue # Already logged in postcode_coordinate()
        entries = nearby_entries(coords)
        entries = filter_distance(entries, coords)
        loc["users"] = entries # entries = (email, token, max_dist, lat, long, dist)
        return_locs.append(loc)       
    return return_locs


def process_changes(avail_state, now_avail):
    new_locs = []
    for locatie_id in now_avail: 
        if locatie_id not in avail_state: # check if available location is new
            avail_state.add(locatie_id) # add to known available locations
            now_avail[locatie_id]["id"] = locatie_id
            new_locs.append(now_avail[locatie_id])
            write_log(f"{locatie_id} became available")
            
    for locatie_id in avail_state: # remove available locations from state that are no longer available
        if locatie_id not in now_avail:
            avail_state.remove(locatie_id)
            write_log(f"{locatie_id} became unavailable")
    
    return avail_state, new_locs


def main():
    write_log("Starting checker")
    if test_run == True:
        write_log("TEST RUN")
    # Setup TLS for email
    context = ssl.create_default_context()
    _ = login_mail_servers(context, is_test = True)
    
    # Check for changes in loop
    avail_state = set()
    while True:
        start_time = datetime.datetime.now() # Log start time
        now_avail = parse_site()
        avail_state, new_locs = process_changes(avail_state, now_avail)
        new_locs = find_nearby_email(new_locs)
        for loc in new_locs:
            notify_users(loc, context)
        
        _ = requests.get("https://hc-ping.com/5b105b06-c003-4ff5-b8ff-b84c21684d84", timeout=10) # Ping to check if it stops working
        loop_time = int((datetime.datetime.now() - start_time).total_seconds()) # Time how long loop took
        remaining = wait_time - loop_time # How long to wait for consistant loop time
        if remaining > 0: 
            for i in range(remaining):
                time.sleep(1)



# Email services
MS = {"sendinblue": {"smtp": "smtp-relay.sendinblue.com", "port": 587, "user": os.environ.get("sendinblue_USER"), "pass": os.environ.get("sendinblue_PASS"), "sleep": 0.2},
      "mailjet": {"smtp": "in-v3.mailjet.com", "port": 587, "user": os.environ.get("mailjet_USER"), "pass": os.environ.get("mailjet_PASS"), "sleep": 0.5},
      "aws": {"smtp": "email-smtp.us-east-2.amazonaws.com", "port": 587, "user": os.environ.get("aws_USER"), "pass": os.environ.get("aws_PASS"), "sleep": 0.2},
      }

# Setup vars
from_address = "pullenbakvaccin-melding-no-reply@wilke.sh"
db_file = "vaccin_users.db"
wait_time = 120 # sec
max_per_loc = 70

# Testings vars
test_run = False
test_mail_service = "sendinblue"

# Global vars
bwnr_API_KEY = os.environ.get("bwnr_API_KEY", default=None)
if not bwnr_API_KEY:
    write_log("postcode API key failed to load from eviron", is_error=True)
    sys.exit("API KEY failed to load")
R = redis.Redis(host="127.0.0.1", port=6379)

# Run main
main()

