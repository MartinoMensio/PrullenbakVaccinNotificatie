from math import sqrt
import time
import pickle
import os, sys
import smtplib, ssl
import datetime
import re
import sqlite3 as sqlite
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup


def timestamp():
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return stamp


def write_log(message, also_print=True):
    '''Write a message to the debug log'''
    with open('debug.log','a') as debug_f:
        debug_f.write(f"{timestamp()} {message}\n")
    if also_print == True:
        print(message)


def test_mail_login(context):
    with smtplib.SMTP_SSL("smtp.gmail.com", port, context=context) as server:
        server.login(gmail, password)

  
def mail_result(resp, region, context):
    subs = user_dict[region]
    if test_run == True:
        subs = ["y.wilke@protonmail.com",]
    write_log(f"Sending email for region {region} to {str(subs)}")
    
    message = MIMEMultipart()
    message["Subject"] = f"Mogelijk vaccin beschikbaar in {region}"
    message["From"] = gmail
    message["To"] = ", ".join(subs) 
    
    resp = f"""<p>Er is mogelijk een vaccin beschikbaar in de buurt van {region}.</a><br>
    Dit is nog een test versie dus mails kunnen soms onterecht verstuurd worden. Feedback geven of uitschrijven kan door te reageren op deze mail.<br>
    Hieronder de locaties binnen 20km van {region}. Check <a href="https://www.prullenbakvaccin.nl#location-selector">https://www.prullenbakvaccin.nl/</a> voor meer informatie.</p><br>
    {resp}"""
    message.attach(MIMEText(resp, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", port, context=context) as server:
        server.login(gmail, password)
        server.sendmail(gmail, subs, message.as_string())


def parse_site():
    postcode_regex = "[\d]{4}[A-Z]{2}"
    now_avail = {}
    
    r = requests.get("https://www.prullenbakvaccin.nl/")
    
    if test_run == True:
        r = pickle.load(open("test_pos_1.p", "rb"))
    
    if r.status_code != 200:
        return {} #TODO log
    soup = BeautifulSoup(r.content, "html.parser")
    soup = soup.find("div", attrs={"id": "locations-container"})
    if not soup: return {} # No available locations
    soup = soup.find_all("div", attrs={"class": "card mb-2"})
    if not soup:
        return {} #TODO log not expected
    
    for elem in soup: # Loop over all doctors now available
        locatie_id = elem.find("h5")["id"]
        if not locatie_id:
            return {} #TODO log
        locatie_text = str(elem.find("p", attrs={"class": "card-text"}))
        match = re.search(postcode_regex, locatie_text)
        if not match:
            return {} #TODO log not expected
        postcode = match.group(0)
        now_avail[locatie_id] = {"postcode": postcode, "html_card": elem}
    return now_avail


def nearby_entries(coords):
    conn = sqlite.connect(f"file:{db_file}?mode=ro", uri=True)
    cur = conn.cursor()
    lat = coords["lat"]; long = coords["long"]
    lat_range = 0.18; long_range = 0.28 # +-20km
    low_lat = lat - lat_range; high_lat = lat + lat_range
    low_long = long - long_range; high_long = long + long_range
    
    cur.execute("""
    SELECT email, token, max_dist, lat, long FROM users
    WHERE lat BETWEEN ? AND ? AND long BETWEEN ? AND ?;
    """, (low_lat, high_lat, low_long, high_long))
    
    entries = cur.fetchall()
    conn.close()
    return entries   


def postcode_coordinate(postcode):
    for i in range(3): # Retry 2 times
        api = "https://bwnr.nl/postcode.php"
        params = {"ak": bwnr_API_KEY,
                  "pc": postcode,
                  "ac": "pc2straat",
                  "tg": "data"}
        resp = requests.get(api, params=params)
        resp = resp.content.decode().split(";")
        if len(resp) == 4:
            break
        elif i == 2:
            return None
        else:
            time.sleep(1)
            
    lat = round(float(resp[2]), 2)
    long = round(float(resp[3]), 2)
    return {"lat": lat, "long": long}


def filter_distance(entries, coords):
    return_entries = []
    for entry in entries:
        lat_dist = abs(entry[3] - coords["lat"]) * 110 * 1000 # Calculatee lat dist in m
        long_dist = abs(entry[4] - coords["long"]) * 70 * 1000 # Calcualte long dist in m
        dist = sqrt(lat_dist**2 + long_dist**2)
        print(dist)
        if dist < entry[2]:
            list(entry).append(dist)
            return_entries.append(entry)
    return return_entries


def find_nearby_email(new_locs):
    return_locs = []
    for loc in new_locs:
        coords = postcode_coordinate(loc["postcode"])
        if not coords:
            continue #TODO log
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
            
    for locatie_id in avail_state: # remove available locations from state that are no longer available
        if locatie_id not in now_avail:
            avail_state.remove(locatie_id)
    
    return avail_state, new_locs


def main():
    write_log("Starting.")
    # Setup TLS for email
    context = ssl.create_default_context()
    test_mail_login(context)

    # Check for changes in loop
    avail_state = set()
    while True:
        now_avail = parse_site()
        #print(f"now avail: {now_avail}")
        avail_state, new_locs = process_changes(avail_state, now_avail)
        #print(f"new_locs: {new_locs}")
        new_locs = find_nearby_email(new_locs)
            
        for i in range(wait_time):
            time.sleep(1)

    """
    # Check for updates in loop
    doctor_dict = {}
    while True:
        # Test run
        if test_run == True:
            write_log("!!!TEST RUN!!!")
        
        # Parse site
        doctors = parse_site(driver)
        doctor_dict = process_changes(doctor_dict, doctors)
        
        
        # Check al user regions
        for region in user_dict:
            # Get data for location
            write_log(f"Checking for region: {region}")
            region_dict, resp = parse_site(region)
            
            # Check for new available
            notify = check_available(region_dict)
            
            # Send email if needed
            if notify == True:
                mail_result(resp, region, context)                        
            else:
                write_log("Nothing to report")
            for i in range(int(wait_time / (len(user_dict)))):
                time.sleep(1)
        """



# Setup vars
neg_resp = "Heeftgeenvaccins"
pos_resp = "Heeftvaccinsbeschikbaar"
db_file = "vaccin_users.db"
wait_time = 300 # sec
port = 465  # For SSL
gmail = "dev.yanowilke@gmail.com"
contact_mail = "dev.yanowilke@gmail.com"
password = input("Password: ")
test_run = True
bwnr_API_KEY = os.environ.get("bwnr_API_KEY", default=None)
if not bwnr_API_KEY:    
    sys.exit("API KEY failed to load")
main()