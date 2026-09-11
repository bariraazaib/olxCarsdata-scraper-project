import re
import json
from datetime import datetime, timedelta


class CleanDataPipeline:
    """Turns raw scraped text into the typed unified schema:
    - stamps scrape_date
    - parses mileage_km / engine_cc from raw text
    - splits model / variant out of the title
    - converts relative 'posted X ago' text into a real listing_date
    - drops the temporary _raw fields before export
    """

    MODEL_MAP = {
        "toyota": ["corolla", "yaris", "vitz", "prius", "passo", "aqua", "camry", "fortuner", "hilux", "land cruiser"],
        "honda": ["civic", "city", "vezel", "brv", "accord", "fit"],
        "suzuki": ["mehran", "cultus", "alto", "wagon r", "swift", "bolan", "ravi", "khyber", "baleno"],
    }

    def process_item(self, item, spider):
        item["scrape_date"] = datetime.utcnow().isoformat()

        item["mileage_km"] = self._parse_number(item.get("_mileage_raw"), unit="km")
        item["engine_cc"] = self._parse_number(item.get("_engine_raw"), unit="cc")

        model, variant = self._split_title(item.get("title"), item.get("make"))
        item["model"] = item.get("_model_raw") or model
        item["variant"] = variant

        item["listing_date"] = self._resolve_date(item.get("_posted_raw"), item["scrape_date"])

        if item.get("features") is not None and not isinstance(item["features"], str):
            item["features"] = json.dumps(item["features"], ensure_ascii=False)

        for temp_field in ("_mileage_raw", "_engine_raw", "_posted_raw", "_model_raw"):
            item.pop(temp_field, None)

        return item

    @staticmethod
    def _parse_number(raw, unit):
        if not raw:
            return None
        digits = re.sub(r"[^\d]", "", raw)
        return int(digits) if digits else None

    def _split_title(self, title, make):
        if not title:
            return None, None
        title_lower = title.lower()

        candidate_makes = [make] if make else list(self.MODEL_MAP.keys())
        for m in candidate_makes:
            if not m:
                continue
            for model in self.MODEL_MAP.get(m.lower(), []):
                if model in title_lower:
                    idx = title_lower.find(model)
                    after = title[idx + len(model):].strip()
                    # strip a trailing 4-digit year from the variant string
                    variant = re.sub(r"\b(19|20)\d{2}\b", "", after).strip(" -")
                    return model.title(), (variant or None)

        # fallback: assume the word right after the make is the model
        if make and make.lower() in title_lower:
            idx = title_lower.find(make.lower()) + len(make)
            rest = title[idx:].strip().split()
            if rest:
                model_guess = rest[0]
                variant_guess = " ".join(rest[1:])
                variant_guess = re.sub(r"\b(19|20)\d{2}\b", "", variant_guess).strip(" -")
                return model_guess, (variant_guess or None)

        return None, None

    @staticmethod
    def _resolve_date(posted_raw, scrape_date_iso):
        if not posted_raw:
            return None
        scrape_dt = datetime.fromisoformat(scrape_date_iso)
        text = posted_raw.lower()

        match = re.search(r"(\d+)\s*(minute|hour|day|week|month)", text)
        if not match:
            return posted_raw  # couldn't parse, keep raw text rather than dropping data

        n, unit = int(match.group(1)), match.group(2)
        delta = {
            "minute": timedelta(minutes=n),
            "hour": timedelta(hours=n),
            "day": timedelta(days=n),
            "week": timedelta(weeks=n),
            "month": timedelta(days=30 * n),
        }[unit]
        return (scrape_dt - delta).date().isoformat()