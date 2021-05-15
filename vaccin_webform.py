import os
import secrets
import sqlite3 as sqlite
from validate_email import validate_email

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
    if len(region) < 2 or len(region) > 50:
        return False
    else:
        return True
        
    
def add_email(region, email, conn, cur):
    # Validate region and email
    if valid_region(region) == False:
        print("bad region")
    if validate_email(email) == False:
        print("bad email")
    
    token = secrets.randbelow(10**9) # Token to unsubscribe
    with conn:
        cur.execute("""INSERT INTO users (region, email, token) VALUES (?,?,?)""", (region, email, token))

db_file = "vaccin_users.db"
conn = sqlite.connect(db_file)
cur = conn.cursor()
create_table()