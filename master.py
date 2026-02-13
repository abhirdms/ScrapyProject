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

def run_all_scrapers():
    print("=" * 70)
    print("STARTING PROPERTY SCRAPING")
    print("=" * 70)
    print()

    all_results = []
    total_properties = 0

    for scraper_name in SCRAPERS:
        print(f"Running scraper: {scraper_name}")
        print("-" * 50)

        try:
            module = importlib.import_module(f"scrapers.{scraper_name}")
            class_name = ''.join(word.title() for word in scraper_name.split('_')) + 'Scraper'
            scraper_class = getattr(module, class_name)

            scraper = scraper_class()
            properties = scraper.run()

            if properties:
                all_results.extend(properties)
                total_properties += len(properties)
                print(f"✓ {scraper_name}: Scraped {len(properties)} properties")
            else:
                print(f"✗ {scraper_name}: No properties found")

        except Exception as e:
            print(f"✗ Error running {scraper_name}: {e}")
            import traceback
            traceback.print_exc()

        print()

    today = datetime.now().strftime("%Y-%m-%d")

    previous_data = []
    previous_urls = set()

    if os.path.exists(CSV_FILE_NAME):
        with open(CSV_FILE_NAME, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            previous_data = list(reader)
            previous_urls = {row["listingUrl"] for row in previous_data if row.get("listingUrl")}

    current_urls = {row["listingUrl"] for row in all_results if row.get("listingUrl")}

    final_data = []

    # Mark New / Old
    for row in all_results:
        listing_url = row.get("listingUrl")

        row["date"] = today

        if listing_url in previous_urls:
            row["status"] = "Old"
        else:
            row["status"] = "New"

        final_data.append(row)

    # Mark Deleted
    deleted_urls = previous_urls - current_urls

    for old_row in previous_data:
        if old_row.get("listingUrl") in deleted_urls:
            old_row["date"] = today
            old_row["status"] = "Deleted"
            final_data.append(old_row)

    if final_data:
        store_data_to_csv(
            final_data,
            filepath=CSV_FILE_NAME,
            mode="overwrite"
        )

    print("=" * 70)
    print("ALL SCRAPERS COMPLETED")
    print(f"Total properties scraped: {total_properties}")
    print(f"Data saved to: {CSV_FILE_NAME}")
    print("=" * 70)


if __name__ == "__main__":
    run_all_scrapers()
