"""
Run this file directly (VS Code's ▷ Run button, or F5) to start the crawl —
no need to type `scrapy crawl ...` in the terminal.

This file must sit in the SAME folder as scrapy.cfg (the project root - one
level above the inner olx_cars/ package folder):

    D:\\Barbra\\ScrapyProjects\\local\\olx_cars\\   <- scrapy.cfg lives here
        run_spider.py                                <- put THIS file here
        olx_cars\\
            spiders\\
                olx_cars_spider.py

Edit SPIDER_NAME / OUTPUT_FILE / MAX_PAGES below as needed, then just
click ▷ Run.
"""

import os
import sys

# Force the project root onto sys.path and tell Scrapy which settings
# module to use, based on THIS FILE's own location - not on whatever
# working directory VS Code / Code Runner happens to launch from.
# This is what fixes "KeyError: Spider not found" when running via
# the Run button instead of the `scrapy` command.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
os.environ.setdefault("SCRAPY_SETTINGS_MODULE", "olx_cars.settings")

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

SPIDER_NAME = "olx_cars"      # must match `name = "..."` inside your spider class
OUTPUT_FILE = "test.csv"      # change this each time to avoid overwrite/lock issues
MAX_PAGES = 3                 # set to None for a full crawl once things look correct

if __name__ == "__main__":
    settings = get_project_settings()
    settings.set("FEEDS", {OUTPUT_FILE: {"format": "csv", "overwrite": True}})

    process = CrawlerProcess(settings)

    spider_kwargs = {}
    if MAX_PAGES is not None:
        spider_kwargs["max_pages"] = MAX_PAGES

    process.crawl(SPIDER_NAME, **spider_kwargs)
    process.start()