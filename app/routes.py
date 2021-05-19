import os
import sys
import secrets
import sqlite3 as sqlite
import re
import time
import datetime
import requests
from validate_email import validate_email

from flask import render_template, request, abort, redirect
from flask_recaptcha import ReCaptcha

from app import app


def timestamp():
    stamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    return stamp


def write_log(message, also_print=False, is_error = False):
    '''Write a message to the debug log'''
    with open('logs/app_debug.log','a') as debug_f:
        debug_f.write(f"[{timestamp()}] {message}\n")
    if is_error == True:
        with open('logs/app_error.log','a') as debug_f:
            debug_f.write(f"[{timestamp()}] {message}\n")
    if also_print == True:
        print(message)

      
def log_new_user(unix_time, postcode, ip, email, token):
    with open('debug/users.log','a') as debug_f:
        debug_f.write(f"{unix_time}\t{postcode}\t{ip}\t{email}\t{token}\n")


def get_ip():
    '''Return ip of user'''
    ip = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
    return ip


def create_table(db_file):
    # Create DB file
    if not os.path.exists(db_file):
        open(db_file,"w").close()
    # Connect to DB
    conn = sqlite.connect(db_file)
    cur = conn.cursor()  
    # Create Table and index
    with conn:
        cur.execute("""CREATE TABLE IF NOT EXISTS users(
                    user_id INTEGER PRIMARY KEY,
                    postcode TEXT COLLATE NOCASE,
                    lat REAL,
                    long REAL,
                    max_dist INTEGER,
                    email TEXT UNIQUE COLLATE NOCASE,
                    token INTEGER);""")
        cur.execute('''CREATE INDEX IF NOT EXISTS idx_lat_long ON users (lat, long);''')


def valid_postcode(postcode):
    postcode = postcode.strip().replace(" ", "").upper()
    postcode_regex = "[\d]{4}[A-Z]{2}"
    match = re.fullmatch(postcode_regex, postcode)
    if not match:
        return False
    else:
        return postcode


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

    
def add_email(postcode, email, max_dist, token, conn):
    # Validate postcode and email
    postcode = valid_postcode(postcode)
    
    if postcode == False:
        return "Postcode niet geldig!"
    
    loc = postcode_coordinate(postcode)
    if not loc:
        return "Probeer een andere postcode in de buurt."
    
    if validate_email(email) == False:
        return "Niet een geldig email adres!"
    
    try:
        with conn:
            conn.execute("""INSERT INTO users (postcode, email, token, lat, long, max_dist) VALUES (?,?,?,?,?,?)""", (postcode, email, token, loc["lat"], loc["long"], max_dist))
    except sqlite.IntegrityError:
        return "Email staat al geregistreerd!"
    except Exception as e:
        write_log(f"Exception while inserting email: {e}", is_error=True)
        return "Iets ging mis. Probeer het opnieuw."
    return True


# Setup vars
db_file = "vaccin_users.db"
dist_dict = {"5km": 6000, "10km": 11000, "15km": 16000}
bwnr_API_KEY = os.environ.get("bwnr_API_KEY", default=None)
if not bwnr_API_KEY:
    sys.exit("API KEY failed to load")
# Global vars
conn = sqlite.connect(db_file, check_same_thread=False)
cur = conn.cursor()

# Prep
create_table(db_file)


# Routing
@app.route('/', methods=['GET'])
def root_page():
    return redirect("/PrullenbakVaccin/aanmelden")


@app.route('/PrullenbakVaccin/aanmelden', methods=['POST', 'GET'])
def signup_page():
    ip = get_ip()
    if request.method == 'GET':
        return render_template('sign_up.html')
    postcode = request.form["postcode"]
    email = request.form["email"]
    max_dist = request.form["max_dist"]
    try: # verify max_dist var and transform to meters
        max_m = dist_dict[max_dist]
    except KeyError:
        max_m = 10000
    token = secrets.randbelow(10**9) # Token to unsubscribe
    
    inserted = add_email(postcode, email, max_m, token, conn)
    if inserted != True:
        return render_template('sign_up.html', postcode=postcode, email=email, error=inserted)
    elif inserted == True:
        write_log("New user signed-up")
        unix_time = int(time.time())
        log_new_user(unix_time, postcode, ip, email, token)
        return render_template('sign_up.html', postcode=postcode, email=email, success=True)


@app.route('/PrullenbakVaccin/unsub', methods=['GET'])
def unsub():
    email = request.args.get('email', None)
    token = request.args.get('token', None)
    with conn:
        cur.execute("""SELECT user_id, email, token FROM users WHERE users.email IS ? AND users.token IS ?""", (email, token))
        hit = cur.fetchone()
        if hit:
            user_id = (hit[0],)
            try:
                cur.execute("""DELETE FROM users WHERE users.user_id IS ?""", (user_id))
                write_log(f"Unsubbed: {email} {token}")
                return render_template('unsub.html', email=email, success=True)
            except Exception as e:
                write_log(f"Exception while removing email: {e}", is_error=True)
                return render_template('unsub.html', email=email, error=True)
        else: # Email or token not found
            write_log(f"No hit on unsub: {email} {token}", is_error=True)
            return render_template('unsub.html', email=email, error=True)


@app.errorhandler(404)
def notfound_handler(e):
    return render_template('404.html', title='Page Not Found'), 404