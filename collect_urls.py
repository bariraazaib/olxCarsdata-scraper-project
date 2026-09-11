"""
Collects car listing URLs using a real browser (via Playwright) by
navigating page-by-page (?page=1, ?page=2, ...). This is needed because
OLX's server returns the SAME first-page content to plain HTTP requests
(like Scrapy's or a simple fetch) regardless of the ?page= value - but a
real browser session with JavaScript actually loads different content
per page. Playwright gives us that real-browser behaviour.

SETUP (run once):
    pip install playwright
    playwright install chromium

USAGE:
    python collect_urls.py

Writes one listing URL per line to listing_urls.txt in the same folder.
Edit TARGET_COUNT / BASE_URL / MAX_PAGES below as needed.
"""

from playwright.sync_api import sync_playwright

BASE_URL = "https://www.olx.com.pk/cars_c84"
TARGET_COUNT = 220           # aim slightly above 200 to allow for dedup/skips
OUTPUT_FILE = "listing_urls.txt"
MAX_PAGES = 10               # safety cap
SCROLL_ROUNDS_PER_PAGE = 3   # a couple of scrolls per page in case that
                             # page itself lazy-loads a few more cards
SCROLL_PAUSE_MS = 900

# Use the Chrome/Edge already installed on this machine instead of having
# Playwright download its own Chromium build - fixes environments where
# that download times out (network/firewall issues). Try "chrome" first;
# if Chrome isn't installed, change this to "msedge" (Edge ships with
# every Windows PC by default).
BROWSER_CHANNEL = "chrome"


def collect_urls():
    urls = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel=BROWSER_CHANNEL)
        page = browser.new_page()

        for page_num in range(1, MAX_PAGES + 1):
            url = BASE_URL if page_num == 1 else f"{BASE_URL}?page={page_num}"
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)  # let the client-side app settle

            for _ in range(SCROLL_ROUNDS_PER_PAGE):
                page.mouse.wheel(0, 4000)
                page.wait_for_timeout(SCROLL_PAUSE_MS)

            hrefs = page.eval_on_selector_all(
                "a[href*='/item/']",
                "els => els.map(e => e.getAttribute('href'))",
            )
            before = len(urls)
            for href in hrefs:
                if href:
                    urls.add(href.split("?")[0])
            after = len(urls)

            print(f"page {page_num}: total collected so far = {after} (+{after - before} new)")

            if after >= TARGET_COUNT:
                break
            if after == before and page_num > 1:
                print("This page added nothing new - stopping early.")
                break

        browser.close()

    return sorted(urls)


if __name__ == "__main__":
    urls = collect_urls()
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for u in urls:
            full_url = u if u.startswith("http") else f"https://www.olx.com.pk{u}"
            f.write(full_url + "\n")
    print(f"\nSaved {len(urls)} listing URLs to {OUTPUT_FILE}")