import os
import re
import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from bs4 import BeautifulSoup

URL = "https://store.blitsgames.com/product/gentleman-studio-goro-nomoru-figure/"
ALERT_THRESHOLDS = [10, 5]

GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
NOTIFY_EMAIL = os.environ["NOTIFY_EMAIL"]


def get_stock_count():
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(URL, headers=headers, timeout=15)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    # Look for patterns like "30 in stock", "Only 10 left", "5 left in stock"
    patterns = [
        r'(\d+)\s+in\s+stock',
        r'only\s+(\d+)\s+left',
        r'(\d+)\s+left\s+in\s+stock',
        r'stock[:\s]+(\d+)',
        r'(\d+)\s+available',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))

    return None


def send_email(stock_count):
    subject = f"⚠️ Stock Alert: Only {stock_count} Goro Nomoru Figure(s) Left!"
    body = f"""
Hi there!

This is your stock alert for the Gentleman Studio – Goro Nomoru Figure.

🔔 Current Stock: {stock_count} remaining

Act fast before it sells out!
👉 {URL}

---
This alert was triggered because stock dropped to {stock_count} (threshold: {', '.join(str(t) for t in ALERT_THRESHOLDS)}).
You will receive another alert at the next threshold.
"""

    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = NOTIFY_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, NOTIFY_EMAIL, msg.as_string())

    print(f"✅ Alert email sent for stock count: {stock_count}")


def main():
    print(f"Checking stock at: {URL}")
    stock = get_stock_count()

    if stock is None:
        print("⚠️  Could not find stock count on the page. The page format may have changed.")
        return

    print(f"📦 Current stock: {stock}")

    for threshold in ALERT_THRESHOLDS:
        if stock <= threshold:
            print(f"🚨 Stock ({stock}) is at or below threshold ({threshold}). Sending alert...")
            send_email(stock)
            break  # Only send one email per run (for the lowest triggered threshold)
    else:
        print(f"✅ Stock ({stock}) is above all thresholds. No alert needed.")


if __name__ == "__main__":
    main()