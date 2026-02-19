"""
Master script to run all scrapers defined in helper.py.
Each scraper saves data to a common CSV file (data/data.csv).
"""
import importlib
import os
import sys

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.csv_handler import store_data_to_csv

from helper import SCRAPERS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

from datetime import datetime
import csv

 # storing the data in website data you can keep the name of the agent company name.
 #  for example if Company Name is Hants Realty , the file name will be hants_realty.csv

CSV_FILE_NAME = os.path.join(BASE_DIR, "website_data", "data.csv")


def load_existing_data():
    existing_map = {}

    if os.path.exists(CSV_FILE_NAME):
        with open(CSV_FILE_NAME, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row.get("listingUrl")
                if url:
                    existing_map[url] = row

    return existing_map


def run_all_scrapers():
    print("=" * 70)
    print("STARTING PROPERTY SCRAPING")
    print("=" * 70)
    print()

    today = datetime.now().strftime("%Y-%m-%d")
    total_properties = 0

    existing_map = load_existing_data()

    for scraper_name in SCRAPERS:
        print(f"Running scraper: {scraper_name}")
        print("-" * 50)

        try:
            module = importlib.import_module(f"scrapers.{scraper_name}")
            class_name = ''.join(word.title() for word in scraper_name.split('_')) + 'Scraper'
            scraper_class = getattr(module, class_name)

            scraper = scraper_class()
            properties = scraper.run()

            if not properties:
                print(f"✗ {scraper_name}: No properties found")
                continue

            # Get agent name from first row (assumed consistent per scraper)
            agent_name = properties[0].get("agentCompanyName", "")

            current_urls = set()
            agent_existing_urls = {
                url for url, row in existing_map.items()
                if row.get("agentCompanyName") == agent_name
            }

            # ---------------- HANDLE NEW / OLD ---------------- #

            for row in properties:
                listing_url = row.get("listingUrl")
                if not listing_url:
                    continue

                current_urls.add(listing_url)
                row["date"] = today

                if listing_url in existing_map:
                    row["status"] = "Old"
                else:
                    row["status"] = "New"

                existing_map[listing_url] = row

            # ---------------- HANDLE DELETED ---------------- #

            deleted_urls = agent_existing_urls - current_urls

            for url in deleted_urls:
                existing_row = existing_map.get(url)
                if existing_row:
                    existing_row["status"] = "Deleted"
                    existing_row["date"] = today
                    existing_map[url] = existing_row

            # ---------------- SAVE AFTER EACH SCRAPER ---------------- #

            store_data_to_csv(
                list(existing_map.values()),
                filepath=CSV_FILE_NAME,
                mode="overwrite"
            )

            total_properties += len(properties)

            print(f"✓ {scraper_name}: Scraped {len(properties)} properties")

        except Exception as e:
            print(f"✗ Error running {scraper_name}: {e}")
            import traceback
            traceback.print_exc()

        print()

    print("=" * 70)
    print("ALL SCRAPERS COMPLETED")
    print(f"Total properties processed this run: {total_properties}")
    print(f"Data saved to: {CSV_FILE_NAME}")
    print("=" * 70)


if __name__ == "__main__":
    run_all_scrapers()
