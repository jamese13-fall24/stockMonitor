# Stock Monitor — Reference Guide

This project automatically checks the stock level of a product page on a schedule, and sends an email alert when stock drops to or below defined thresholds. It runs entirely in the cloud for free using GitHub Actions and ScraperAPI.

This document is written as a reference guide so you can build a similar monitor for any product on any site from scratch.

---

## How It Works (The Full Picture)

```
GitHub Actions (cron schedule)
    → runs check_stock.py
        → ScraperAPI fetches the product page (with JS rendering)
            → BeautifulSoup parses the HTML for stock count
                → compares stock against thresholds
                    → sends Gmail alert if new threshold crossed
                        → saves state to stock_state.json
                            → GitHub Actions commits state file back to repo
```

The key insight is that GitHub Actions serves as both the scheduler and the runtime environment — no server required. The state file committed back to the repo is how memory is persisted between runs.

---

## Files in This Project

```
repo/
├── check_stock.py        # Main script
├── stock_state.json      # Tracks which thresholds have been alerted
└── .github/
    └── workflows/
        └── stock-monitor.yml   # GitHub Actions workflow
```

---

## Step 1 — Understand the Target Site

Before writing any code, you need to answer two questions about your target product page:

**1. Does the site block bots?**

Most e-commerce sites do. A simple `requests.get()` will return a 403 Forbidden. Signs of bot protection: Cloudflare, requiring JS to render content, or blocking known cloud IP ranges (like GitHub's). If you get a 403, you need a scraping proxy like ScraperAPI.

**2. Where is the stock number in the HTML?**

Open the product page, right-click the stock number, and click "Inspect". Look at the element. Common patterns:

- A `<span>` or `<p>` with a class like `stock`, `availability`, or a theme-specific class (e.g. `woostify-single-product-stock-label`)
- The `max` attribute on a `<input type="number" name="quantity">` — this is reliable because WooCommerce always sets it to the current stock count
- Inline `<script>` tags containing `"stock_quantity": 30` as part of a JSON blob

**Important:** Some stock numbers are only rendered after a user interaction (e.g. selecting a product variation). Check whether the number appears on initial page load or only after clicking something. If it only appears after a click, you either need to simulate the interaction or find an alternative element (like the quantity input `max`) that is present without interaction.

**How to find the right element for any site:**

Add this debug block to your parser function and run it once:

```python
# Print all elements whose class name contains "stock"
for el in soup.find_all(class_=re.compile(r'stock|quantity|inventory|avail', re.I)):
    print(el.name, el.get('class'), el.get_text(strip=True)[:100])

# Print all lines of visible text containing stock-related words
for line in soup.get_text(" ").splitlines():
    line = line.strip()
    if re.search(r'in stock|left|available|qty', line, re.I) and line:
        print(line[:120])
```

Remove the debug block once you've found the right element.

---

## Step 2 — Set Up ScraperAPI

ScraperAPI routes your requests through residential IPs and can render JavaScript before returning the HTML. The free tier gives you 1,000 requests/month.

1. Sign up at [scraperapi.com](https://www.scraperapi.com) (no credit card needed)
2. Copy your API key from the dashboard

The API works by passing your target URL as a parameter:

```python
params = {
    "api_key": YOUR_KEY,
    "url": "https://example.com/product/",
    "render": "true",      # Enable JS rendering — required for dynamic content
    "country_code": "us",  # Use US IPs
}
response = requests.get("https://api.scraperapi.com/", params=params, timeout=60)
html = response.text
```

**When to use `render: true`:** Always use it if the stock number is loaded by JavaScript. It costs more API credits but is necessary for modern e-commerce sites. If the site is simple static HTML, you can skip it to save credits.

**Handling ScraperAPI 500 errors:** These are transient server errors on ScraperAPI's end. Add retry logic:

```python
def get_stock_count(retries=3, delay=30):
    import time
    for attempt in range(1, retries + 1):
        try:
            html = fetch_via_scraperapi()
            return parse_stock_from_html(html)
        except Exception as e:
            print("Attempt " + str(attempt) + " failed: " + str(e))
            if attempt < retries:
                time.sleep(delay)
    return None
```

---

## Step 3 — Parse the Stock Number

Once you know which HTML element contains the stock count, write a targeted parser using BeautifulSoup:

```python
from bs4 import BeautifulSoup
import re

def parse_stock_from_html(html):
    soup = BeautifulSoup(html, "html.parser")

    # Option A: Target a specific class name
    el = soup.find("span", class_="your-stock-class-here")
    if el:
        match = re.search(r'(\d+)', el.get_text())
        if match:
            return int(match.group(1))

    # Option B: Use the quantity input's max attribute (WooCommerce sites)
    qty = soup.find("input", {"name": "quantity", "class": re.compile(r"qty")})
    if qty and qty.get("max"):
        return int(qty["max"])

    # Option C: Search inline script tags for JSON stock data
    for script in soup.find_all("script"):
        src = script.string or ""
        match = re.search(r'"stock_quantity"\s*:\s*(\d+)', src)
        if match:
            return int(match.group(1))

    return None
```

**Common pitfalls:**
- Broad regex patterns (e.g. just `r'(\d+)'`) will accidentally match prices, IDs, or other numbers on the page. Always require context words like "in stock" or use a specific element class.
- The `max` attribute on quantity inputs is the most reliable signal on WooCommerce stores — it's always present and always reflects real-time stock.

---

## Step 4 — Threshold Logic and State

The goal is to send **one email per threshold**, not one per run. This requires persisting state between runs.

**State file (`stock_state.json`):**

```json
{"alerted_thresholds": []}
```

Initialize it with an empty list. As thresholds are crossed, their values are added to the list. The logic:

```python
ALERT_THRESHOLDS = [25, 20, 15, 10, 5]

alerted = set(state.get("alerted_thresholds") or [])

# Find thresholds stock has crossed that haven't been alerted yet
new_alerts = [t for t in sorted(ALERT_THRESHOLDS, reverse=True)
              if stock <= t and t not in alerted]

for threshold in new_alerts:
    send_email(stock, threshold)
    alerted.add(threshold)

save_state({"alerted_thresholds": list(alerted)})
```

**Recovery logic** — if stock goes back up above a threshold (e.g. restocked), remove it from the alerted set so you'll be notified again if it drops below that threshold in the future:

```python
# Use strict > (not >=) so a threshold isn't reset while stock sits exactly at it
recovered = [t for t in alerted if stock > t]
if recovered:
    alerted -= set(recovered)
    save_state({"alerted_thresholds": list(alerted)})
```

**Critical operator choices:**
- Use `stock <= t` when checking if a threshold is crossed (at or below)
- Use `stock > t` when checking if stock has recovered (strictly above)
- Getting these wrong causes thresholds to either never fire or to reset immediately

**Manually setting initial state:** If stock is already below some thresholds when you first deploy, manually edit `stock_state.json` to pre-populate the already-crossed thresholds, otherwise you'll get a burst of emails on the first run.

---

## Step 5 — Email Alerts via Gmail

Use Gmail's SMTP server with an App Password (not your real Gmail password).

**Setup:**
1. Enable 2-Step Verification on your Google account
2. Go to Google Account → Security → App Passwords
3. Create a new App Password, name it anything, copy the 16-character key

```python
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email(stock_count, threshold):
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = NOTIFY_EMAIL
    msg["Subject"] = "Stock Alert: dropped to " + str(stock_count)
    msg.attach(MIMEText("Stock is now at " + str(stock_count), "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, NOTIFY_EMAIL, msg.as_string())
```

The sender and recipient can be the same Gmail address.

---

## Step 6 — GitHub Actions Workflow

The workflow file lives at `.github/workflows/your-name.yml`. It has two parts: the schedule and the commit step.

**Schedule syntax (cron):**
```yaml
on:
  schedule:
    - cron: '0 * * * *'   # Every hour (minute hour day month weekday)
  workflow_dispatch:        # Also allow manual runs
```

Common cron patterns:
- Every 30 minutes: `*/30 * * * *`
- Every hour: `0 * * * *`
- Every day at 9am UTC: `0 9 * * *`

Note: GitHub Actions cron runs in UTC. Adjust for your timezone.

**Free tier limits:** GitHub Actions gives you 2,000 minutes/month on free accounts. Each run of this script takes under 2 minutes, so hourly runs (720/month) are well within limits.

**Committing state back to the repo:**

This is what makes memory persist between runs. The workflow checks out the repo, runs the script (which modifies `stock_state.json`), then commits and pushes the change back.

```yaml
- name: Commit state file
  run: |
    git config user.name "github-actions[bot]"
    git config user.email "github-actions[bot]@users.noreply.github.com"
    git add stock_state.json
    if git diff --staged --quiet; then
      echo "No changes to commit."
    else
      git commit -m "Update stock state"
      git push
    fi
```

**Required permission:** Go to repo → Settings → Actions → General → Workflow permissions → select "Read and write permissions". Without this, the push will fail silently.

**Passing secrets to the script:**

Never hardcode API keys or passwords. Store them as GitHub Secrets (Settings → Secrets and Variables → Actions) and pass them as environment variables:

```yaml
- name: Run stock checker
  env:
    GMAIL_USER: ${{ secrets.GMAIL_USER }}
    GMAIL_APP_PASSWORD: ${{ secrets.GMAIL_APP_PASSWORD }}
    NOTIFY_EMAIL: ${{ secrets.NOTIFY_EMAIL }}
    SCRAPERAPI_KEY: ${{ secrets.SCRAPERAPI_KEY }}
  run: python check_stock.py
```

In the Python script, read them with `os.environ["KEY_NAME"]`.

---

## Secrets Reference

| Secret Name | What It Is |
|---|---|
| `GMAIL_USER` | Your Gmail address |
| `GMAIL_APP_PASSWORD` | 16-char App Password from Google |
| `NOTIFY_EMAIL` | Email to send alerts to (can be same as GMAIL_USER) |
| `SCRAPERAPI_KEY` | API key from scraperapi.com |

---

## Debugging Tips

**Test the scraper locally before deploying:**
```python
import requests
from bs4 import BeautifulSoup

html = requests.get("https://api.scraperapi.com/", params={
    "api_key": "YOUR_KEY", "url": "YOUR_URL", "render": "true"
}, timeout=60).text

soup = BeautifulSoup(html, "html.parser")
print(soup.find("span", class_="your-class").get_text())
```

**If you get a 403:** The site is blocking GitHub/ScraperAPI IPs. Try adding `"country_code": "us"` or `"premium": "true"` to ScraperAPI params (premium uses higher-quality residential IPs, costs more credits).

**If the element isn't found:** The content may load after a user interaction. Check if there's an alternative element (like the quantity input) that loads without interaction, or look in inline `<script>` tags for the data as JSON.

**If state isn't being saved:** Check that workflow permissions are set to "Read and write". Add `echo "--- git status ---" && git status` before the commit step to see what's happening.

**If you get repeat emails:** The state file isn't being committed. Check the Actions log for the "Commit state file" step. Also verify the threshold comparison operators (`<=` for triggering, `>` for recovery).

**To pause the monitor:** Go to Actions → your workflow → "..." menu → Disable workflow. Re-enable it the same way.

---

## Adapting This for a Different Site

1. Find the stock element using browser DevTools → use the debug snippet to confirm it's in the scraped HTML
2. Update `PRODUCT_URL` and the parser in `parse_stock_from_html()`
3. Update `ALERT_THRESHOLDS` to match the stock levels you care about
4. Set `stock_state.json` to `{"alerted_thresholds": []}` and deploy
5. Run manually once to confirm the stock number is read correctly before enabling the schedule
