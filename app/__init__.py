from flask import Flask
from flask_bootstrap import Bootstrap

import dotenv
dotenv.load_dotenv()

app = Flask(__name__)
Bootstrap(app)
from app import routes
