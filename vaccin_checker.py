import time
import pickle
import os, sys
import smtplib, ssl
import datetime
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


def create_user_dict(file):
    user_dict = {}
    with open(file, "r") as user_f:
        for line in user_f:
            line = line.split("\t")
            user_mail = line[0].strip()
            user_region = line[1].strip()
            try:
                user_dict[user_region].append(user_mail)
            except KeyError:
                user_dict[user_region] = [user_mail,]
    return user_dict

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


def parse_site(location):
    region_dict = {}
    s = requests.Session()
    r = s.get("https://www.prullenbakvaccin.nl/")
    soup = BeautifulSoup(r.content, "html.parser")
    token = soup.find("input", attrs={"name": "_token"})["value"]
    payload = {"location": location, "_token": token}
    r = s.post("https://www.prullenbakvaccin.nl/", data=payload)
    if r.status_code != 200:
        sys.exit(f"HTTP code: {r.status_code}") #TODO log and notify
    soup = BeautifulSoup(r.content, "html.parser")
    soup = soup.find("div", attrs= {"id": "locations-container"})
    resp = str(soup)
    soup = soup.find_all("h5")
    for x in soup:
        locatie = x["id"]
        status = x.find("small").string.extract().replace("\n", " ").replace(" ", "")
        region_dict[locatie] = status.strip()
    return region_dict, resp


def check_available(region_dict):
    notify = False
    vaccin_state = pickle.load(open("state.p", "rb")) # Read vaccine state
    
    write_log(f"Result: {region_dict}")
    write_log(f"State: {vaccin_state}")
    
    for locatie in region_dict:
        if locatie in vaccin_state:
            if vaccin_state[locatie] != region_dict[locatie]: # If different from last state
                if region_dict[locatie] != neg_resp: # Maybe a vaccin available
                    notify = True
            vaccin_state[locatie] = region_dict[locatie]
        else:
            if region_dict[locatie] != neg_resp: # Maybe a vaccin available
                notify = True
            vaccin_state[locatie] = region_dict[locatie] # Set state for new location
    
    pickle.dump(vaccin_state, open("state.p", "wb")) # Write vaccin state
    return notify


def main():
    write_log("Starting.")
    # Setup TLS for email
    context = ssl.create_default_context()
    test_mail_login(context)
    
    # Load previous state
    if os.path.isfile("state.p"):
        vaccin_state = pickle.load(open("state.p", "rb"))
    else:   
        vaccin_state = dict()
        pickle.dump(vaccin_state, open("state.p", "wb"))
    
    # Check for updates in loop
    while True:
        # Test run
        if test_run == True:
            write_log("!!!TEST RUN!!!")
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


# Users dict
user_dict = create_user_dict("users.txt")

# Setup vars
neg_resp = "Heeftgeenvaccins"
pos_resp = "Heeftvaccinsbeschikbaar"
wait_time = 300 # sec
port = 465  # For SSL
gmail = "dev.yanowilke@gmail.com"
contact_mail = "dev.yanowilke@gmail.com"
password = input("Password: ")
test_run = False

main()