"""
Collects car listing URLs using a real browser (via Playwright).

WHY MULTIPLE SEED URLS?
OLX only lets you paginate ~40-50 pages (~1,000-1,200 listings) deep into
ANY single search/category view, no matter how many total results it claims.
To get more of the 70,000+ total cars, we run the SAME page-by-page collector
against many different filtered views (one per brand, and further split by
popular models for the biggest brands) and merge + de-duplicate the results.

This will NOT capture literally every listing (some very obscure model/city
combinations may still be missed) but should capture a large majority.

SETUP (run once):
    pip install playwright
    playwright install chromium

USAGE:
    python collect_urls.py

Writes one listing URL per line to listing_urls.txt in the same folder.
"""

from playwright.sync_api import sync_playwright

OUTPUT_FILE = "listing_urls.txt"
TARGET_PER_URL = 1200          # OLX's practical pagination ceiling per view
MAX_PAGES_PER_URL = 60         # safety cap per seed URL
SCROLL_ROUNDS_PER_PAGE = 3
SCROLL_PAUSE_MS = 900

# --- Brands with a moderate number of listings: one URL each is enough ---
SMALL_BRANDS = [
    "mitsubishi", "changan", "haval", "mg", "faw", "jaecoo", "mercedes",
    "chevrolet", "dfsk", "prince", "mazda", "daewoo", "proton", "chery",
    "united", "subaru", "audi", "bmw", "jeep", "peugeot", "jetour", "byd",
    "deepal", "jac", "lexus", "gwm", "isuzu", "baic", "fiat", "volkswagen",
    "datsun", "dongfeng", "ssangyong", "tesla", "ford",
]

# --- Brands with 1,200+ listings: split further by popular model keyword ---
BIG_BRANDS = {
    "suzuki": ["mehran", "cultus", "alto", "swift", "bolan", "wagon-r",
               "liana", "every", "khyber", "ravi", "baleno", "fx", "ciaz"],
    "toyota": ["corolla", "vitz", "yaris", "aqua", "surf", "prius", "hilux",
               "raize", "premio", "passo", "prado", "fortuner", "land-cruiser",
               "c-hr"],
    "honda": ["city", "civic", "vezel", "accord", "br-v", "reborn", "crv"],
    "daihatsu": ["cuore", "mira", "move", "hijet"],
    "hyundai": ["santro", "tucson", "sonata", "elantra"],
    "nissan": ["sunny", "dayz", "note", "serena"],
    "kia": ["sportage", "picanto", "stonic", "sorento"],
}


def build_seed_urls():
    urls = []

    # Nationwide "all cars" view as a base pass
    urls.append("https://www.olx.com.pk/cars_c84")

    # One URL per small/medium brand
    for brand in SMALL_BRANDS:
        urls.append(f"https://www.olx.com.pk/{brand}-cars_c84?filter=make_eq_{brand}")

    # Big brands: one URL per popular model, plus a catch-all for the brand
    for brand, models in BIG_BRANDS.items():
        urls.append(f"https://www.olx.com.pk/{brand}-cars_c84?filter=make_eq_{brand}")
        for model in models:
            urls.append(
                f"https://www.olx.com.pk/{brand}-cars_c84/q-{model}?filter=make_eq_{brand}"
            )

    return urls


def collect_from_url(page, base_url, all_urls):
    found_here = 0
    consecutive_empty = 0
    for page_num in range(1, MAX_PAGES_PER_URL + 1):
        url = base_url if page_num == 1 else f"{base_url}{'&' if '?' in base_url else '?'}page={page_num}"
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"  page {page_num}: failed to load ({e}) - skipping")
            break

        page.wait_for_timeout(1500)
        for _ in range(SCROLL_ROUNDS_PER_PAGE):
            page.mouse.wheel(0, 4000)
            page.wait_for_timeout(SCROLL_PAUSE_MS)

        hrefs = page.eval_on_selector_all(
            "a[href*='/item/']",
            "els => els.map(e => e.getAttribute('href'))",
        )
        before = len(all_urls)
        for href in hrefs:
            if href:
                all_urls.add(href.split("?")[0])
        after = len(all_urls)
        new_here = after - before
        found_here += new_here

        print(f"  page {page_num}: total so far (this URL) ~{found_here}, grand total = {after} (+{new_here} new)")

        if found_here >= TARGET_PER_URL:
            break

        if new_here == 0 and page_num > 1:
            consecutive_empty += 1
        else:
            consecutive_empty = 0

        if consecutive_empty >= 3:
            print("  3 pages in a row with no new listings - moving to next seed URL")
            break


def collect_urls():
    all_urls = set()
    seed_urls = build_seed_urls()
    print(f"Collecting from {len(seed_urls)} seed URLs...\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        for i, base_url in enumerate(seed_urls, start=1):
            print(f"[{i}/{len(seed_urls)}] {base_url}")
            collect_from_url(page, base_url, all_urls)
            print()

        browser.close()

    return sorted(all_urls)


if __name__ == "__main__":
    urls = collect_urls()
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for u in urls:
            full_url = u if u.startswith("http") else f"https://www.olx.com.pk{u}"
            f.write(full_url + "\n")
    print(f"\nSaved {len(urls)} unique listing URLs to {OUTPUT_FILE}")
