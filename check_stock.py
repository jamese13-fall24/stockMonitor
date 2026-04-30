import os
import re
import json
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup

PRODUCT_URL = "https://store.blitsgames.com/product/gentleman-studio-goro-nomoru-figure/"
PRODUCT_SLUG = "gentleman-studio-goro-nomoru-figure"
STORE_BASE = "https://store.blitsgames.com"
ALERT_THRESHOLDS = [10, 5]

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
NOTIFY_EMAIL = os.environ["NOTIFY_EMAIL"]
SCRAPERAPI_KEY = os.environ["SCRAPERAPI_KEY"]


def fetch_via_scraperapi():
    api_url = "https://api.scraperapi.com/"
    params = {
        "api_key": SCRAPERAPI_KEY,
        "url": PRODUCT_URL,
        "render": "true",
        "country_code": "us",
    }
    print("Fetching via ScraperAPI (JS rendering)...")
    response = requests.get(api_url, params=params, timeout=60)
    response.raise_for_status()
    return response.text


def parse_stock_from_html(html):
    soup = BeautifulSoup(html, "html.parser")

    # Debug: show all elements with stock-related classes
    print("--- DEBUG: stock-related elements ---")
    for el in soup.find_all(class_=re.compile(r'stock|quantity|inventory|avail', re.I)):
        cls = el.get('class')
        txt = el.get_text(strip=True)[:100]
        print("  TAG=" + el.name + " CLASS=" + str(cls) + " TEXT=" + txt)

    # Debug: show lines containing stock keywords
    full_text = soup.get_text(" ")
    for line in full_text.splitlines():
        line = line.strip()
        if re.search(r'in stock|left in|available|qty', line, re.I) and line:
            print("  LINE: " + line[:120])
    print("--- END DEBUG ---")

    # 1. Check JSON-LD structured data
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict):
                    offer = item.get("offers", {})
                    if isinstance(offer, list):
                        offer = offer[0] if offer else {}
                    inventory = offer.get("inventoryLevel", {})
                    if isinstance(inventory, dict) and "value" in inventory:
                        return int(inventory["value"])
        except Exception:
            pass

    # 2. WooCommerce stock element
    stock_el = soup.find(class_=re.compile(r'stock|availability', re.I))
    if stock_el:
        text = stock_el.get_text()
        match = re.search(r'(\d+)', text)
        if match:
            return int(match.group(1))

    # 3. Broad text search
    patterns = [
        r'(\d+)\s+in\s+stock',
        r'only\s+(\d+)\s+left',
        r'(\d+)\s+left\s+in\s+stock',
        r'(\d+)\s+available',
        r'stock[:\s]+(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            return int(match.group(1))

    return None


def get_stock_count():
    try:
        html = fetch_via_scraperapi()
        stock = parse_stock_from_html(html)
        if stock is not None:
            return stock
        print("Page fetched but stock number not found.")
    except Exception as e:
        print("ScraperAPI failed: " + str(e))
    return None


def send_email(stock_count):
    subject = "Stock Alert: Only " + str(stock_count) + " Goro Nomoru Figure(s) Left!"
    body = (
        "Hi there!\n\n"
        "This is your automated stock alert for the Gentleman Studio - Goro Nomoru Figure.\n\n"
        "Current Stock: " + str(stock_count) + " remaining\n\n"
        "Act fast before it sells out!\n"
        + PRODUCT_URL + "\n\n"
        "---\n"
        "Thresholds monitored: " + ", ".join(str(t) for t in sorted(ALERT_THRESHOLDS)) + "\n"
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
            print("Stock (" + str(stock) + ") is at or below threshold (" + str(threshold) + "). Sending alert...")
            send_email(stock)
            break
    else:
        print("Stock (" + str(stock) + ") is above all thresholds. No alert needed.")


if __name__ == "__main__":
    main()
