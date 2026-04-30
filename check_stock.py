import os
import re
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup

PRODUCT_URL = "https://store.blitsgames.com/product/gentleman-studio-goro-nomoru-figure/"
ALERT_THRESHOLDS = [30, 20, 10, 5]

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
NOTIFY_EMAIL = os.environ["NOTIFY_EMAIL"]
SCRAPERAPI_KEY = os.environ["SCRAPERAPI_KEY"]


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

    # Target the exact stock label element used by the Woostify theme
    stock_label = soup.find("span", class_="woostify-single-product-stock-label")
    if stock_label:
        text = stock_label.get_text(strip=True)
        print("Stock label found: " + text)
        m = re.search(r'(\d+)', text)
        if m:
            return int(m.group(1))

    print("Stock label element not found in page.")
    return None


def get_stock_count():
    try:
        html = fetch_via_scraperapi()
        stock = parse_stock_from_html(html)
        if stock is not None:
            return stock
    except Exception as e:
        print("ScraperAPI failed: " + str(e))
    return None


def send_email(stock_count):
    subject = "Stock Alert: Only " + str(stock_count) + " Goro Nomoru Figure(s) Left!"
    body = (
        "Hi there!\n\n"
        "Stock alert for: Gentleman Studio - Goro Nomoru Figure\n\n"
        "Current Stock: " + str(stock_count) + " remaining\n\n"
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
    print("Alert email sent for stock count: " + str(stock_count))


def main():
    print("Checking stock at: " + PRODUCT_URL)
    stock = get_stock_count()

    if stock is None:
        print("Could not determine stock count. Manual check recommended.")
        return

    print("Current stock: " + str(stock))

    for threshold in sorted(ALERT_THRESHOLDS, reverse=True):
        if stock <= threshold:
            print("ALERT: Stock (" + str(stock) + ") hit threshold (" + str(threshold) + "). Sending email...")
            send_email(stock)
            break
    else:
        print("Stock (" + str(stock) + ") is above all thresholds. No alert needed.")


if __name__ == "__main__":
    main()
