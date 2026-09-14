import re
import json
import scrapy
from urllib.parse import urljoin

from ..items import OlxCarItem


class OlxCarsSpider(scrapy.Spider):
    name = "olx_cars"
    allowed_domains = ["olx.com.pk"]

    # Pass a different start URL at runtime if you want, e.g.:
    # scrapy crawl olx_cars -a start_url="https://www.olx.com.pk/cars_c84/q-used-car"
    start_urls = [
        "https://www.olx.com.pk/cars_c84/q-used-car",
    ]

    custom_settings = {
        "DOWNLOAD_DELAY": 1.5,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
    }

    def __init__(self, start_url=None, max_pages=None, url_file=None,
                 start_index=None, end_index=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if start_url:
            self.start_urls = [start_url]
        self.max_pages = int(max_pages) if max_pages else None
        self._page_count = 0
        self.url_file = url_file
        # Slice of the url_file to process this run (0-based, end exclusive)
        # - used for GitHub Actions chunking so one run only does a portion
        # of the full URL list, staying well under the 6-hour job limit.
        self.start_index = int(start_index) if start_index is not None else 0
        self.end_index = int(end_index) if end_index is not None else None

    def start_requests(self):
        self.logger.info(f"DEBUG: self.url_file = {self.url_file!r}")
        # If a url_file is given (produced by collect_urls.py), skip the
        # search-results crawling entirely and go straight to each listing's
        # detail page - this is how we get past OLX's infinite-scroll limit.
        # Usage: scrapy crawl olx_cars -a url_file=listing_urls.txt -O out.csv
        if self.url_file:
            with open(self.url_file, "r", encoding="utf-8") as f:
                urls = [line.strip() for line in f if line.strip()]

            total = len(urls)
            chunk = urls[self.start_index:self.end_index]
            self.logger.info(
                f"Loaded {total} URLs from {self.url_file}; "
                f"processing slice [{self.start_index}:{self.end_index}] "
                f"= {len(chunk)} URLs this run"
            )
            for url in chunk:
                listing_id = self._extract_listing_id(url)
                if not listing_id:
                    continue
                yield scrapy.Request(
                    url,
                    callback=self.parse_detail,
                    meta={"listing_id": listing_id},
                )
        else:
            for url in self.start_urls:
                yield scrapy.Request(url, callback=self.parse)

    async def start(self):
        # Newer Scrapy versions (2.13+) call this async generator instead of
        # start_requests(). We keep both defined so it works either way -
        # this one just delegates to the same logic above.
        for request in self.start_requests():
            yield request

    # ------------------------------------------------------------------
    # LISTING (search results) PAGE
    # These selectors are confirmed against a real OLX card sample.
    # ------------------------------------------------------------------
    def parse(self, response):
        cards = response.xpath("//li[.//a[contains(@href, '/item/')]]")
        for card in cards:
            href = card.css("a[href*='/item/']::attr(href)").get()
            if not href:
                continue
            item_url = urljoin(str(response.url), str(href))

            listing_id = self._extract_listing_id(item_url)
            title = self._clean(card.css('[aria-label="Title"] h2::text').get())
            price_text = self._clean(card.css('[aria-label="Price"] span::text').get())
            year = self._clean(card.css('[aria-label="Year"] span::text').get())
            mileage_raw = self._clean(card.css('[aria-label="Mileage"] span::text').get())
            fuel_type = self._clean(card.css('[aria-label="FuelType"] span::text').get())
            location = self._clean(card.css('[aria-label="Location"]::text').get())
            posted_raw = self._clean(card.css('[aria-label="Creation date"]::text').get())

            if not listing_id:
                continue

            meta = {
                "listing_id": listing_id,
                "title": title,
                "price_text": price_text,
                "year": year,
                "mileage_raw": mileage_raw,
                "fuel_type": fuel_type,
                "listing_city": location,
                "posted_raw": posted_raw,
            }
            yield scrapy.Request(item_url, callback=self.parse_detail, meta=meta)

        self._page_count += 1
        if self.max_pages and self._page_count >= self.max_pages:
            return

        next_page = response.css(
            'a[aria-label="Next"]::attr(href), a[data-aut-id="pageArrowRight"]::attr(href)'
        ).get()
        if next_page:
            next_url = urljoin(str(response.url), str(next_page))
            yield scrapy.Request(next_url, callback=self.parse)

    def parse_detail(self, response):
        item = OlxCarItem()
        meta = response.meta

        jsonld = self._extract_jsonld(response)

        details = {
            **self._extract_quick_facts(response),
            **self._extract_details_dict(response),
            **jsonld,
        }

        item["listing_id"] = meta["listing_id"]
        item["url"] = response.url
        item["platform"] = "olx"

        title = jsonld.get("_title") or self._clean(response.css("h1::text").get()) or meta.get("title")
        item["title"] = title

        item["price"] = jsonld.get("_price") or self._parse_price(meta.get("price_text"))

        item["year"] = self._to_int(details.get("year")) or self._to_int(meta.get("year"))

        item["_mileage_raw"] = (
            details.get("mileage")
            or meta.get("mileage_raw")
            or details.get("km's driven")
        )
        item["_engine_raw"] = (
            details.get("engine capacity")
            or details.get("engine displacement")
            or details.get("engine capacity (cc)")
        )

        item["fuel_type"] = details.get("fuel") or meta.get("fuel_type")
        item["transmission"] = details.get("transmission") or self._label_fallback(response, "Transmission")
        item["condition"] = details.get("condition") or self._label_fallback(response, "Condition")
        item["body_type"] = details.get("body type") or self._label_fallback(response, "Body Type")
        item["color"] = (
            details.get("color") or details.get("colour")
            or self._label_fallback(response, "Color", "Colour")
        )
        item["assembly"] = details.get("assembly") or self._label_fallback(response, "Assembly")
        item["registered_in"] = (
            details.get("registration city") or details.get("registered city")
            or self._label_fallback(response, "Registration city", "Registered City")
        )
        item["make"] = (
            details.get("make") or self._label_fallback(response, "Make") or self._guess_make(title)
        )

        item["_model_raw"] = details.get("model")

        item["listing_city"] = meta.get("listing_city") or self._extract_location(response)
        item["_posted_raw"] = meta.get("posted_raw") or self._extract_posted(response)

        seller_name, seller_type, seller_verified = self._extract_seller(response)
        item["seller_name"] = seller_name
        item["seller_type"] = seller_type
        item["seller_verified"] = seller_verified

        item["description_text"] = jsonld.get("_description") or self._clean(
            " ".join(
                response.css(
                    '[aria-label="Description"] ::text, '
                    '[data-aut-id="itemDescriptionText"] ::text'
                ).getall()
            )
        )

        item["features"] = self._extract_features(response)

        images = response.css('img[src*="olx"]::attr(src), img::attr(data-src)').getall()
        item["images"] = self._normalize_images(images)

        yield item

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _clean(value):
        if not value:
            return None
        value = re.sub(r"\s+", " ", value).strip()
        return value or None

    @staticmethod
    def _extract_listing_id(url):
        match = re.search(r"iid-(\d+)", url)
        return match.group(1) if match else None

    @staticmethod
    def _to_int(value):
        if value is None:
            return None
        digits = re.sub(r"[^\d]", "", str(value))
        return int(digits) if digits else None

    @staticmethod
    def _parse_price(price_text):
        if not price_text:
            return None
        text = price_text.lower().replace(",", "")
        num_match = re.search(r"[\d.]+", text)
        if not num_match:
            return None
        number = float(num_match.group())
        if "crore" in text:
            return int(number * 1_00_00_000)
        if "lac" in text:
            return int(number * 100_000)
        if "thousand" in text:
            return int(number * 1_000)
        return int(number)

    def _extract_jsonld(self, response):
        result = {}
        scripts = response.css('script[type="application/ld+json"]::text').getall()
        for raw in scripts:
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            nodes = data.get("@graph", [data]) if isinstance(data, dict) else data
            if not isinstance(nodes, list):
                nodes = [nodes]
            for node in nodes:
                if not isinstance(node, dict):
                    continue
                entity = node.get("mainEntity") if "mainEntity" in node else node
                if not isinstance(entity, dict):
                    continue
                types = entity.get("@type")
                types = types if isinstance(types, list) else [types]
                if "Car" not in types and "Product" not in types:
                    continue

                if entity.get("name"):
                    result["_title"] = entity["name"]
                if entity.get("description"):
                    result["_description"] = entity["description"]
                brand = entity.get("brand")
                if isinstance(brand, dict) and brand.get("name"):
                    result["make"] = brand["name"]
                if entity.get("model"):
                    result["model"] = entity["model"]
                if entity.get("vehicleModelDate"):
                    result["year"] = str(entity["vehicleModelDate"])
                if entity.get("fuelType"):
                    result["fuel"] = entity["fuelType"]
                if entity.get("vehicleTransmission"):
                    result["transmission"] = entity["vehicleTransmission"]
                if entity.get("color"):
                    result["color"] = entity["color"]
                if entity.get("bodyType"):
                    result["body type"] = entity["bodyType"]
                mileage = entity.get("mileageFromOdometer")
                if isinstance(mileage, dict) and mileage.get("value"):
                    result["mileage"] = str(mileage["value"])

                offers = entity.get("offers")
                if isinstance(offers, list):
                    offers = offers[0] if offers else None
                if isinstance(offers, dict) and offers.get("price"):
                    result["_price"] = self._to_int(offers["price"])

                for prop in entity.get("additionalProperty", []) or []:
                    if not isinstance(prop, dict):
                        continue
                    name = (prop.get("name") or "").strip().lower()
                    value = prop.get("value")
                    if name and value:
                        result[name] = str(value)

                return result
        return result

    def _label_fallback(self, response, *labels):
        for label in labels:
            value = response.xpath(
                f'//span[normalize-space(string(.))="{label}"]'
                f'/following-sibling::*[1]//text()'
            ).get()
            cleaned = self._clean(value)
            if cleaned and cleaned.lower() != label.lower():
                return cleaned
        return None

    def _extract_quick_facts(self, response):
        result = {}
        rows = response.css('div._948d9e0a.dcd9316f._95d4067f')
        for row in rows:
            texts = [self._clean(s.xpath('string(.)').get()) for s in row.css('span')]
            texts = [t for t in texts if t]
            if len(texts) >= 2:
                result[texts[0].lower()] = texts[1]
        return result

    def _extract_details_dict(self, response):
        result = {}
        rows = response.css('div._90eadc7c')
        for row in rows:
            cd_blocks = row.css('div._0272c9dc')
            if not cd_blocks:
                continue
            cd = cd_blocks[0]
            value_el = cd.css('span._4ad4c394')
            value_text = self._clean(value_el.xpath('string(.)').get()) if value_el else None
            label = None
            for span in cd.css('span'):
                if "_4ad4c394" in (span.attrib.get("class") or ""):
                    continue
                text = self._clean(span.xpath('string(.)').get())
                if text:
                    label = text
                    break
            if label and value_text:
                result[label.lower()] = value_text
        return result

    def _extract_location(self, response):
        cities = [
            "Karachi", "Lahore", "Islamabad", "Rawalpindi", "Faisalabad",
            "Multan", "Gujranwala", "Peshawar", "Sialkot", "Hyderabad",
            "Sargodha", "Wah", "Bahawalpur", "Abbottabad", "Gujrat",
            "Sahiwal", "Sheikhupura", "Jhelum", "Mardan", "Quetta",
        ]
        head_text = " ".join(response.css("h1, h1 ~ *")[:5].xpath(".//text()").getall())
        for city in cities:
            if re.search(rf"\b{city}\b", head_text, re.I):
                return city
        return None

    def _extract_posted(self, response):
        match = response.xpath(
            '//*[contains(text(), "ago") or contains(text(), "Today") or contains(text(), "Yesterday")]/text()'
        ).re_first(r"[\w\s]*\bago\b|\bToday\b|\bYesterday\b")
        return self._clean(match)

    def _extract_seller(self, response):
        name = None
        profile_links = response.css('a[href*="/profile/"]')

        for link in profile_links:
            spans = [self._clean(s.xpath("string(.)").get()) for s in link.css("span")]
            spans = [s for s in spans if s]
            candidates = [s for s in spans if s.lower() != "posted by"]
            if candidates:
                name = candidates[0]
                break

        profile_block_text = " ".join(
            response.css('a[href*="/profile/"] ::text, a[href*="/profile/"] + * ::text').getall()
        )
        seller_verified = bool(re.search(r"verified", profile_block_text, re.I)) if name else None
        seller_type = None
        if name:
            seller_type = "Dealer" if re.search(r"dealer|business|motors?\b", name, re.I) else "Private"

        return name, seller_type, seller_verified

    def _extract_features(self, response):
        result = {}
        groups = response.css(
            'div[aria-label="Features"] div._948d9e0a._68e344b0._95d4067f > div'
        )
        for group in groups:
            category = self._clean(
                group.css('div._948d9e0a.c085df57._371e9918 span::text').get()
            )
            tags = [self._clean(t) for t in group.css('div.ee08ff9c span::text').getall()]
            tags = [t for t in tags if t]
            if category and tags:
                result[category] = tags
        return result if result else None

    @staticmethod
    def _normalize_images(urls):
        seen, cleaned = set(), []
        for u in urls:
            if not u:
                continue
            base = re.sub(r"[-_](s|thumb|small)?\d*x\d*", "", u)
            if base not in seen:
                seen.add(base)
                cleaned.append(base)
        return cleaned or None

    @staticmethod
    def _guess_make(title):
        if not title:
            return None
        known_makes = [
            "Toyota", "Honda", "Suzuki", "Daihatsu", "Nissan", "Hyundai",
            "KIA", "Mercedes", "Changan", "Mazda", "DFSK", "JAC", "Jetour",
            "Mitsubishi", "FAW", "MG", "Haval", "Chevrolet", "Audi", "Proton",
            "BMW",
        ]
        for make in known_makes:
            if make.lower() in title.lower():
                return make
        return None
