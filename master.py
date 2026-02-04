"""
Master script to run all scrapers defined in helper.py.
Each scraper saves data to a common CSV file (data/data.csv).
"""
import importlib
import os
import sys

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from helper import SCRAPERS


def run_all_scrapers():
    """Run all scrapers defined in helper.py."""
    print("=" * 70)
    print("STARTING PROPERTY SCRAPING")
    print("=" * 70)
    print()
    
    total_properties = 0
    
    for scraper_name in SCRAPERS:
        print(f"Running scraper: {scraper_name}")
        print("-" * 50)
        
        try:
            # Import the scraper module dynamically
            module = importlib.import_module(f"scrapers.{scraper_name}")
            
            # Get the scraper class (assumes class name is PascalCase of module name + Scraper)
            # e.g., knight_commercial -> KnightCommercialScraper
            class_name = ''.join(word.title() for word in scraper_name.split('_')) + 'Scraper'
            scraper_class = getattr(module, class_name)
            
            # Create and run the scraper
            scraper = scraper_class()
            properties = scraper.run()
            
            if properties:
                total_properties += len(properties)
                print(f"✓ {scraper_name}: Scraped {len(properties)} properties")
            else:
                print(f"✗ {scraper_name}: No properties found")
                
        except Exception as e:
            print(f"✗ Error running {scraper_name}: {e}")
            import traceback
            traceback.print_exc()
        
        print()
    
    print("=" * 70)
    print("ALL SCRAPERS COMPLETED")
    print(f"Total properties scraped: {total_properties}")
    print("Data saved to: data/data.csv")
    print("=" * 70)


if __name__ == "__main__":
    run_all_scrapers()
