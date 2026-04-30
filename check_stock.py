import os
import re
import json
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup

PRODUCT_URL = "https://store.blitsgames.com/product/gentleman-studio-goro-nomoru-figure/"
ALERT_THRESHOLDS = [25, 20, 15, 10, 5]
STATE_FILE = "stock_state.json"

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
NOTIFY_EMAIL = os.environ["NOTIFY_EMAIL"]
SCRAPERAPI_KEY = os.environ["SCRAPERAPI_KEY"]


def load_state():
    """Load the last alerted threshold from state file."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"last_alerted_threshold": None}


def save_state(state):
    """Save state back to file."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)
    print("State saved: " + str(state))


def fetch_via_scraperapi():
    params = {
        "api_key": SCRAPERAPI_KEY,
        "url": PRODUCT_URL,
        "render": "true",
        "country_code": "us",
    }
    print("Fetching via ScraperAPI...")
    r = requests.get("https://api.scraperapi.com/", params=params, timeout=60)
    r.raise_for_status()
    return r.text


def parse_stock_from_html(html):
    soup = BeautifulSoup(html, "html.parser")
    qty_input = soup.find("input", {"name": "quantity", "class": re.compile(r"qty")})
    if qty_input and qty_input.get("max"):
        val = qty_input["max"]
        print("Stock from quantity input max: " + val)
        return int(val)
    print("Quantity input not found in page.")
    return None


def get_stock_count():
    try:
        html = fetch_via_scraperapi()
        return parse_stock_from_html(html)
    except Exception as e:
        print("ScraperAPI failed: " + str(e))
    return None


def send_email(stock_count, threshold):
    subject = "Stock Alert: Goro Nomoru Figure dropped below " + str(threshold) + " (" + str(stock_count) + " left)"
    body = (
        "Hi there!\n\n"
        "Stock alert for: Gentleman Studio - Goro Nomoru Figure\n\n"
        "Current Stock: " + str(stock_count) + " remaining\n"
        "Triggered threshold: below " + str(threshold) + "\n\n"
        "Act fast!\n" + PRODUCT_URL + "\n\n"
        "---\nThresholds monitored: " + ", ".join(str(t) for t in sorted(ALERT_THRESHOLDS)) + "\n"
    )
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = NOTIFY_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, NOTIFY_EMAIL, msg.as_string())
    print("Alert email sent: below " + str(threshold) + ", stock=" + str(stock_count))


def main():
    print("Checking stock at: " + PRODUCT_URL)
    stock = get_stock_count()

    if stock is None:
        print("Could not determine stock count. Manual check recommended.")
        return

    print("Current stock: " + str(stock))

    state = load_state()
    last_alerted = state.get("last_alerted_threshold")
    print("Last alerted threshold: " + str(last_alerted))

    # Find the highest threshold that stock has dropped below
    triggered = None
    for threshold in sorted(ALERT_THRESHOLDS, reverse=True):
        if stock < threshold:
            triggered = threshold
            break

    if triggered is None:
        print("Stock is above all thresholds. No alert needed.")
        # Reset state if stock has recovered above all thresholds
        if last_alerted is not None:
            save_state({"last_alerted_threshold": None})
        return

    if triggered == last_alerted:
        print("Already alerted for threshold " + str(triggered) + ". No new email needed.")
        return

    # New threshold crossed — send email and save state
    print("New threshold crossed: below " + str(triggered) + ". Sending alert...")
    send_email(stock, triggered)
    save_state({"last_alerted_threshold": triggered})


if __name__ == "__main__":
    main()
