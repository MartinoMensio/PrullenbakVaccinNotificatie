import os
import secrets
import sqlite3 as sqlite
from validate_email import validate_email

from flask import render_template, request, abort
from flask_recaptcha import ReCaptcha

from app import app

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
                    region TEXT COLLATE NOCASE,
                    email TEXT UNIQUE COLLATE NOCASE,
                    token INTEGER);""")
        cur.execute('''CREATE INDEX IF NOT EXISTS idx_user_region 
                    ON users (region);''')


def valid_region(region):
    region = region.strip()
    region = region.lower()
    if len(region) < 2 or len(region) > 50:
        return False
    else:
        return region
        
    
def add_email(region, email, conn):
    # Validate region and email
    region = valid_region(region)
    if region == False:
        return "Plaatsnaam niet geldig"
    if validate_email(email) == False:
        return "Niet een geldig email adres!"
    
    token = secrets.randbelow(10**9) # Token to unsubscribe
    try:
        with conn:
            conn.execute("""INSERT INTO users (region, email, token) VALUES (?,?,?)""", (region, email, token))
    except sqlite.IntegrityError:
        return "Email staat al geregistreerd!"
    return True


db_file = "vaccin_users.db"
conn = sqlite.connect(db_file, check_same_thread=False)
cur = conn.cursor()
create_table(db_file)


# Routing
@app.route('/PrullenbakVaccin/aanmelden', methods=['POST', 'GET'])
def signup_page():
    if request.method == 'GET':
        return render_template('sign_up.html')
    region = request.form["region"]
    email = request.form["email"]
    inserted = add_email(region, email, conn)
    if inserted != True:
        return render_template('sign_up.html', region=region, email=email, error=inserted)
    elif inserted == True:
        return render_template('sign_up.html', region=region, email=email, success=True)
    return render_template('sign_up.html', region=region, email=email)


@app.route('/PrullenbakVaccin/unsub', methods=['GET'])
def unsub():
    email = request.args.get('email', None)
    token = request.args.get('token', None)
    print(email, token)
    with conn:
        cur.execute("""SELECT user_id, email, token FROM users WHERE users.email IS ? AND users.token IS ?""", (email, token))
        hit = cur.fetchone()
        print(hit)
        if hit:
            user_id = (hit[0],)
            print(user_id)
            try:
                cur.execute("""DELETE FROM users WHERE users.user_id IS ?""", (user_id))
                return render_template('unsub.html', email=email, success=True)
            except Exception as exception:
                pass #TODO log
                print(exception)
            
        return render_template('unsub.html', email=email, error=True)

@app.errorhandler(404)
def notfound_handler(e):
    return render_template('404.html', title='Page Not Found'), 404