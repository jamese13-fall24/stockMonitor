import os
import re
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup

PRODUCT_URL = "https://store.blitsgames.com/product/gentleman-studio-goro-nomoru-figure/"
ALERT_THRESHOLDS = [10, 5]

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
NOTIFY_EMAIL = os.environ["NOTIFY_EMAIL"]
SCRAPERAPI_KEY = os.environ["SCRAPERAPI_KEY"]


def fetch_via_scraperapi(wait_ms=5000):
    params = {
        "api_key": SCRAPERAPI_KEY,
        "url": PRODUCT_URL,
        "render": "true",
        "country_code": "us",
        "wait_for_selector": ".woostify-single-product-stock-label",
        "wait": wait_ms,
    }
    print("Fetching via ScraperAPI (wait=" + str(wait_ms) + "ms)...")
    r = requests.get("https://api.scraperapi.com/", params=params, timeout=90)
    r.raise_for_status()
    return r.text


def parse_stock_from_html(html):
    soup = BeautifulSoup(html, "html.parser")

    # Primary: Woostify stock label
    stock_label = soup.find("span", class_="woostify-single-product-stock-label")
    if stock_label:
        text = stock_label.get_text(strip=True)
        print("Stock label found: " + text)
        m = re.search(r'(\d+)', text)
        if m:
            return int(m.group(1))

    # Fallback: any element containing "in stock" text
    for el in soup.find_all(string=re.compile(r'\d+\s+in\s+stock', re.I)):
        m = re.search(r'(\d+)\s+in\s+stock', el, re.I)
        if m:
            print("Stock from text node: " + el.strip())
            return int(m.group(1))

    # Debug: show all class names that contain "stock"
    print("=== DEBUG: all elements with 'stock' in class ===")
    for el in soup.find_all(class_=re.compile(r'stock', re.I)):
        print("  " + el.name + " | " + str(el.get('class')) + " | " + el.get_text(strip=True)[:80])
    print("=== END DEBUG ===")

    return None


def get_stock_count():
    # Try with increasing wait times
    for wait in [5000, 10000]:
        try:
            html = fetch_via_scraperapi(wait_ms=wait)
            stock = parse_stock_from_html(html)
            if stock is not None:
                return stock
            print("Retrying with longer wait...")
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
