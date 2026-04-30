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


def fetch_via_woocommerce_api():
    """WooCommerce stores expose a REST API. Try to get stock from it directly."""
    print("Trying WooCommerce REST API...")
    api_url = f"{STORE_BASE}/wp-json/wc/v3/products"
    params = {"slug": PRODUCT_SLUG, "per_page": 1}
    response = requests.get(api_url, params=params, timeout=15)
    response.raise_for_status()
    products = response.json()
    if products and isinstance(products, list):
        product = products[0]
        stock = product.get("stock_quantity")
        print(f"WooCommerce API returned stock: {stock}")
        return stock
    return None


def fetch_via_scraperapi():
    """Use ScraperAPI's direct API endpoint with JS rendering enabled."""
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
    """Parse stock count from page HTML using multiple patterns."""
    soup = BeautifulSoup(html, "html.parser")

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

    # 2. WooCommerce stock status elements
    stock_el = soup.find(class_=re.compile(r"stock|availability", re.I))
    if stock_el:
        text = stock_el.get_text()
        match = re.search(r'(\d+)', text)
        if match:
            return int(match.group(1))

    # 3. Broad text search
    text = soup.get_text(" ", strip=True)
    patterns = [
        r'(\d+)\s+in\s+stock',
        r'only\s+(\d+)\s+left',
        r'(\d+)\s+left\s+in\s+stock',
        r'(\d+)\s+available',
        r'stock[:\s]+(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))

    return None


def get_stock_count():
    # Method 1: WooCommerce REST API
    try:
        stock = fetch_via_woocommerce_api()
        if stock is not None:
            return stock
    except Exception as e:
        print(f"WooCommerce API failed: {e}")

    # Method 2: ScraperAPI with JS rendering
    try:
        html = fetch_via_scraperapi()
        stock = parse_stock_from_html(html)
        if stock is not None:
            return stock
        print("Page fetched but stock number not found. Snippet:")
        print(html[:2000])
    except Exception as e:
        print(f"ScraperAPI failed: {e}")

    return None


def send_email(stock_count):
    subject = f"Stock Alert: Only {stock_count} Goro Nomoru Figure(s) Left!"
    body = f"""Hi there!

This is your automated stock alert for the Gentleman Studio - Goro Nomoru Figure.

Current Stock: {stock_count} remaining

Act fast before it sells out!
{PRODUCT_URL}

---
Thresholds monitored: {', '.join(str(t) for t in sorted(ALERT_THRESHOLDS))}
"""
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = NOTIFY_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, NOTIFY_EMAIL, msg.as_string())

    print(f"Alert email sent for stock count: {stock_count}")


def main():
    print(f"Checking stock at: {PRODUCT_URL}")
    stock = get_stock_count()

    if stock is None:
        print("Could not determine stock count. Manual check recommended.")
        return

    print(f"Current stock: {stock}")

    for threshold in sorted(ALERT_THRESHOLDS, reverse=True):
        if stock <= threshold:
            print(f"Stock ({stock}) is at or below threshold ({threshold}). Sending alert...")
            send_email(stock)
            break
    else:
        print(f"Stock ({stock}) is above all thresholds. No alert needed.")


if __name__ == "__main__":
    main()
