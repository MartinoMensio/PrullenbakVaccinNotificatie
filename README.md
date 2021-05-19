# PrullenbakVaccinNotificatie

## Installation

You need to get an API token from [BWNR](https://bwnr.nl/pcapi.php) and set in in the environment. You can create a file named `.env` in this directory and insert the following content:

```text
bwnr_API_KEY=YOUR_API_TOKEN_THAT_YOU_RECEIVED_FROM_BWNR
```

The requirements can be installed by running `pip install -r requirements.txt`

## Usage

You can run the web server with `uwsgi --http :9000 prullenbakvaccin.ini`
