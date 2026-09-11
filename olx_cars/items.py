import scrapy


class OlxCarItem(scrapy.Item):
    # --- READY (scraped as-is) ---
    listing_id = scrapy.Field()
    url = scrapy.Field()
    title = scrapy.Field()
    make = scrapy.Field()
    year = scrapy.Field()
    price = scrapy.Field()
    fuel_type = scrapy.Field()
    transmission = scrapy.Field()
    condition = scrapy.Field()
    body_type = scrapy.Field()
    color = scrapy.Field()
    registered_in = scrapy.Field()
    images = scrapy.Field()

    # --- ADD (constants / new fields) ---
    platform = scrapy.Field()
    scrape_date = scrapy.Field()
    listing_city = scrapy.Field()
    listing_date = scrapy.Field()
    seller_type = scrapy.Field()
    seller_name = scrapy.Field()
    seller_verified = scrapy.Field()
    description_text = scrapy.Field()

    # --- PARSE (cleaned in pipeline) ---
    model = scrapy.Field()
    variant = scrapy.Field()
    mileage_km = scrapy.Field()
    engine_cc = scrapy.Field()
    features = scrapy.Field()

    # --- PENDING (may be missing on OLX; keep NULL if absent) ---
    assembly = scrapy.Field()

    # raw fields kept temporarily for the pipeline to clean, dropped before export
    _mileage_raw = scrapy.Field()
    _engine_raw = scrapy.Field()
    _posted_raw = scrapy.Field()
    _model_raw = scrapy.Field()