"""
Knight Commercial London Property Scraper.

This scraper extracts property listings from Knight Commercial London website
across all property types (To Let, For Sale, Investment).
"""
import os
import time
import re
import logging
import shutil
from typing import List, Dict, Optional
from selenium import webdriver

from utils import store_data_to_csv
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, 
    NoSuchElementException,
    StaleElementReferenceException
)
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# ============================================================
# CONFIGURATION - All settings embedded in scraper
# ============================================================
BASE_URL = "https://www.knightcommerciallondon.co.uk/"
DROPDOWN_OPTIONS = ["To Let", "For Sale", "Investment"]
CSV_FILENAME = "data/data.csv"
SCROLL_PAUSE_TIME = 5
MAX_SCROLL_ATTEMPTS = 8  # More attempts to ensure all properties load
REQUEST_DELAY = 2
PAGE_LOAD_TIMEOUT = 30
HEADLESS_MODE = True
WINDOW_SIZE = "1920,1080"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
AGENT_COMPANY_NAME = "Knight Commercial London"


# ============================================================
# LOGGER SETUP
# ============================================================
def setup_logger(name: str) -> logging.Logger:
    """Setup a simple logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                                               datefmt='%Y-%m-%d %H:%M:%S'))
        logger.addHandler(handler)
    return logger





# ============================================================
# SCRAPER CLASS
# ============================================================
class KnightCommercialScraper:
    """Scraper for Knight Commercial London properties."""
    
    def __init__(self):
        """Initialize the scraper."""
        self.logger = setup_logger('KnightCommercial')
        self.driver = None
        self.properties_scraped = 0
        self.properties_data = []  # Collect all property data to save at the end
        
    def setup_driver(self):
        """Set up and configure the Selenium WebDriver."""
        self.logger.info("Setting up Chrome WebDriver...")
        
        chrome_options = Options()
        
        if HEADLESS_MODE:
            chrome_options.add_argument('--headless=new')
        
        chrome_options.add_argument(f'--window-size={WINDOW_SIZE}')
        chrome_options.add_argument(f'user-agent={USER_AGENT}')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-gpu')
        
        # For WSL environments, try chromium-browser first
        import shutil
        import subprocess
        chromium_path = shutil.which('chromium-browser')
        chrome_path = shutil.which('google-chrome')
        
        if chromium_path:
            chrome_options.binary_location = chromium_path
            self.logger.info(f"Using chromium-browser at: {chromium_path}")
        elif chrome_path:
            chrome_options.binary_location = chrome_path
            self.logger.info(f"Using google-chrome at: {chrome_path}")
        else:
            error_msg = """
            Chrome/Chromium browser not found!
            
            Please install Chrome or Chromium:
            
            For Ubuntu/WSL:
              sudo apt-get update
              sudo apt-get install -y chromium-browser
            
            Or install Google Chrome:
              wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
              sudo apt install ./google-chrome-stable_current_amd64.deb
            """
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)
        
        try:
            # For snap-installed chromium, we need to use a specific driver version
            # Instead of auto-detecting, use a compatible ChromeDriver version
            try:
                # Try to get browser version
                if chromium_path:
                    result = subprocess.run(
                        [chromium_path, '--version'], 
                        capture_output=True, 
                        text=True, 
                        timeout=5
                    )
                    browser_version = result.stdout.strip()
                    self.logger.info(f"Browser version: {browser_version}")
            except Exception as e:
                self.logger.warning(f"Could not detect browser version: {e}")
            
            # Use ChromeDriverManager with specific version for better compatibility
            from webdriver_manager.chrome import ChromeDriverManager
            from webdriver_manager.core.os_manager import ChromeType
            
            # For chromium, specify the chrome type
            if chromium_path:
                self.logger.info("Installing ChromeDriver for Chromium...")
                driver_manager = ChromeDriverManager(chrome_type=ChromeType.CHROMIUM)
            else:
                self.logger.info("Installing ChromeDriver for Google Chrome...")
                driver_manager = ChromeDriverManager()
            
            service = Service(driver_manager.install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
            
            self.logger.info("WebDriver setup complete")
        except Exception as e:
            self.logger.error(f"Failed to initialize WebDriver: {e}")
            
            # Fallback: try using system ChromeDriver if available
            chromedriver_path = shutil.which('chromedriver')
            if chromedriver_path:
                self.logger.info(f"Trying system chromedriver at: {chromedriver_path}")
                try:
                    service = Service(chromedriver_path)
                    self.driver = webdriver.Chrome(service=service, options=chrome_options)
                    self.driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
                    self.logger.info("WebDriver setup complete using system chromedriver")
                    return
                except Exception as e2:
                    self.logger.error(f"System chromedriver also failed: {e2}")
            
            raise RuntimeError(f"""
            Failed to set up ChromeDriver. 
            
            Try installing chromium-chromedriver:
              sudo apt-get install -y chromium-chromedriver
            
            Original error: {e}
            """)
    
    def navigate_to_homepage(self):
        """Navigate to the Knight Commercial homepage."""
        self.logger.info(f"Navigating to {BASE_URL}")
        self.driver.get(BASE_URL)
        time.sleep(3)  # Wait for page to load
    
    def navigate_to_property_type(self, property_type: str) -> str:
        """
        Navigate to a specific property type and return the corresponding sale type.
        
        Args:
            property_type: One of "To Let", "For Sale", "Investment"
            
        Returns:
            Sale type string for CSV
        """
        # Map dropdown options to URL paths
        url_mapping = {
            "To Let": "/properties/to-let",
            "For Sale": "/properties/for-sale",
            "Investment": "/search/?activeListingType=I&isAscending=false&sortProperty=price" # Updated URL for Investment
        }
        
        # Map to sale type for CSV
        sale_type_map = {
            "To Let": "To Let",
            "For Sale": "For Sale",
            "Investment": "Investment"  # Fixed: was incorrectly set to "To Let"
        }
        
        url_path = url_mapping.get(property_type)
        if not url_path:
            self.logger.error(f"Unknown property type: {property_type}")
            return "To Let"
        
        full_url = f"{BASE_URL.rstrip('/')}{url_path}"
        self.logger.info(f"Navigating to {property_type} properties: {full_url}")
        
        self.driver.get(full_url)
        
        # Wait for JavaScript to render properties (the page uses dynamic loading)
        self.logger.info("Waiting for properties to load via JavaScript...")
        try:
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            # Wait up to 15 seconds for property links to appear
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/listing/']"))
            )
            self.logger.info("Property links detected, page loaded successfully")
        except Exception as e:
            self.logger.warning(f"Timeout waiting for property links: {e}")
            # Try scrolling down to trigger lazy load
            self.driver.execute_script("window.scrollTo(0, 500);")
            time.sleep(3)
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(3)
        
        time.sleep(2)  # Additional wait for all properties to render
        
        # For Investment page, refresh to ensure properties load correctly
        if property_type == "Investment":
            self.logger.info("Refreshing Investment page to ensure properties load...")
            self.driver.refresh()
            time.sleep(5)
        
        return sale_type_map.get(property_type, "To Let")
    
    def scroll_and_load_all_properties(self) -> List[str]:
        """
        Scroll down the page to load all properties via infinite scroll.
        
        Returns:
            List of property detail page URLs
        """
        self.logger.info("Starting infinite scroll to load all properties...")
        
        property_urls = set()
        no_change_count = 0
        scroll_count = 0
        
        while no_change_count < MAX_SCROLL_ATTEMPTS:
            # Get current property URLs
            current_urls = self._extract_property_urls()
            before_count = len(property_urls)
            property_urls.update(current_urls)
            after_count = len(property_urls)
            
            # Check if new properties were loaded
            if after_count == before_count:
                no_change_count += 1
                self.logger.info(f"No new properties loaded (attempt {no_change_count}/{MAX_SCROLL_ATTEMPTS})")
            else:
                no_change_count = 0
                self.logger.info(f"Found {after_count - before_count} new properties (total: {after_count})")
            
            # Scroll to bottom with smooth scrolling for lazy load
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            scroll_count += 1
            time.sleep(6)  # Increased wait time for lazy loading
            
            # Scroll up slightly then back down to trigger any lazy loaders
            self.driver.execute_script("window.scrollBy(0, -800);")
            time.sleep(2)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(4)
        
        self.logger.info(f"Scroll complete. Total properties found: {len(property_urls)} (after {scroll_count} scrolls)")
        return list(property_urls)
    
    def _extract_property_urls(self) -> List[str]:
        """
        Extract property detail page URLs from the current listing page.
        
        Returns:
            List of URLs
        """
        urls = []
        try:
            # Find all property listing links (using /listing/ in the URL)
            property_elements = self.driver.find_elements(
                By.CSS_SELECTOR, 
                "a[href*='/listing/']"
            )
            
            for element in property_elements:
                try:
                    href = element.get_attribute('href')
                    if href and '/listing/' in href and 'sid-' in href:
                        urls.append(href)
                except StaleElementReferenceException:
                    continue
            
        except Exception as e:
            self.logger.warning(f"Error extracting property URLs: {e}")
        
        return list(set(urls))  # Remove duplicates
    
    def extract_property_details(self, url: str, sale_type: str) -> Dict:
        """
        Extract all property details from a property page.
        
        Args:
            url: Property detail page URL
            sale_type: "For Sale" or "To Let"
            
        Returns:
            Dictionary with all extracted fields
        """
        self.logger.info(f"Extracting details from: {url}")
        
        try:
            self.driver.get(url)
            time.sleep(2)  # Wait for page load
            
            data = {
                'listingUrl': url,
                'displayAddress': self._extract_address(),
                'price': self._extract_price(sale_type),
                'propertySubType': self._extract_property_type(),
                'propertyImage': self._extract_images(),
                'detailedDescription': self._extract_description(),
                'sizeFt': self._extract_size_sqft(),
                'sizeAc': '',  # Empty for now - for future scrapers
                'postalCode': self._extract_postcode(),
                'brochureUrl': self._extract_brochure_url(),
                'agentCompanyName': AGENT_COMPANY_NAME,
                'agentName': self._extract_agent_name(),
                'agentCity': self._extract_agent_city(),
                'agentEmail': self._extract_agent_email(),
                'agentPhone': self._extract_agent_phone(),
                'agentStreet': self._extract_agent_street(),
                'agentPostcode': self._extract_agent_postcode(),
                'tenure': self._extract_tenure(),
                'saleType': sale_type
            }
            
            self.logger.info(f"Successfully extracted property: {data['displayAddress']}")
            return data
            
        except Exception as e:
            self.logger.error(f"Error extracting property details from {url}: {e}")
            return None
    
    def _safe_find_text(self, selectors: List[str], default: str = "") -> str:
        """
        Safely find and extract text from elements using multiple selectors.
        
        Args:
            selectors: List of CSS selectors to try
            default: Default value if not found
            
        Returns:
            Extracted text or default
        """
        for selector in selectors:
            try:
                element = self.driver.find_element(By.CSS_SELECTOR, selector)
                text = element.text.strip()
                if text:
                    return text
            except NoSuchElementException:
                continue
        return default
    
    def _extract_address(self) -> str:
        """Extract the full address from the location H3 element."""
        try:
            # XPath from user: /html/body/div[2]/div[3]/.../h3
            # Try multiple approaches
            h3_elements = self.driver.find_elements(By.TAG_NAME, 'h3')
            for h3 in h3_elements:
                text = h3.text.strip()
                # Address usually contains a postcode pattern
                if re.search(r'[A-Z]{1,2}\d{1,2}\s?\d[A-Z]{2}', text, re.IGNORECASE):
                    return text
            
            # Fallback to first h1
            h1 = self.driver.find_element(By.TAG_NAME, 'h1')
            return h1.text.strip()
        except Exception as e:
            self.logger.warning(f"Error extracting address: {e}")
            return ""
    
    def _extract_price(self, sale_type: str) -> str:
        """Extract price, handling both 'Price' (For Sale) and 'Rent' (To Let) labels."""
        try:
            # Different labels based on sale type
            search_labels = []
            if sale_type == "For Sale":
                search_labels = ["Price"]
            elif sale_type == "To Let":
                search_labels = ["Rent"]
            else:  # Investment
                search_labels = ["Price", "Rent"]
            
            # Find all divs with price/rent information
            divs = self.driver.find_elements(By.TAG_NAME, 'div')
            
            for div in divs:
                text = div.text.strip()
                # Check if text starts with one of our labels
                for label in search_labels:
                    if text.startswith(label):
                        # Extract just the number part, removing label and any text after
                        # e.g., "Rent\n£130,000 PAX" -> "130000"
                        parts = text.split('\n')
                        if len(parts) > 1:
                            price_text = parts[1]  # Get the line after "Price" or "Rent"
                            # Remove currency symbol and commas, keep only digits
                            # Also remove text like "PAX", "per annum", etc
                            price_clean = re.sub(r'[^\d]', '', price_text.split()[0] if price_text else '')
                            return price_clean
            
            return ""
            
        except Exception as e:
            self.logger.warning(f"Error extracting price: {e}")
            return ""
    
    def _extract_property_type(self) -> str:
        """Extract property sub-type from the H1 heading (second line after TO LET/FOR SALE/INVESTMENT).""" 
        try:
            # Find H1 in property-details-rte-component
            h1_elements = self.driver.find_elements(By.TAG_NAME, 'h1')
            
            for h1 in h1_elements:
                text = h1.text.strip()
                # The H1 format is:
                # "TO LET\nA CONTEMPORARY SPLIT LEVEL PENTHOUSE OFFICE..."
                # or "INVESTMENT\nFREEHOLD INVESTMENT - A SUBSTANTIAL MIXED-USE..."
                lines = text.split('\n')
                if len(lines) >= 2:
                    first_line = lines[0].strip().upper()
                    # Check if first line indicates property type
                    if first_line in ['TO LET', 'FOR SALE', 'INVESTMENT']:
                        # Return second line (the actual property description)
                        description = lines[1].strip()
                        if description:
                            return description
            
            # Fallback: try body text pattern
            body_text = self.driver.find_element(By.TAG_NAME, 'body').text
            type_match = re.search(r'(?:TO LET|FOR SALE|INVESTMENT)[\s\n]+([A-Z][^\n]+)', body_text)
            if type_match:
                return type_match.group(1).strip()
            
            return ""
            
        except Exception as e:
            self.logger.warning(f"Error extracting property type: {e}")
            return ""
    
    def _extract_images(self) -> str:
        """
        Extract all property images.
        
        Returns:
            String representation of Python list
        """
        images = []
        try:
            img_elements = self.driver.find_elements(
                By.CSS_SELECTOR,
                ".gallery img, .property-images img, [class*='gallery'] img, [class*='slider'] img"
            )
            
            for img in img_elements:
                src = img.get_attribute('src')
                if src and 'http' in src:
                    images.append(src)
        except Exception as e:
            self.logger.warning(f"Error extracting images: {e}")
        
        # Return as string representation of list
        return str(list(set(images)))
    
    def _extract_description(self) -> str:
        """Extract detailed property description from the description paragraph."""
        try:
            # User XPath points to property-details-rte-component p tags
            # Find all paragraphs in property details sections
            paragraphs = self.driver.find_elements(By.CSS_SELECTOR, "property-details-rte-component p")
            
            descriptions = []
            for p in paragraphs:
                text = p.text.strip()
                if text and len(text) > 50:  # Only substantial paragraphs
                    descriptions.append(text)
            
            if descriptions:
                return " ".join(descriptions)
            
            # Fallback to body text extraction
            body_text = self.driver.find_element(By.TAG_NAME, 'body').text
            desc_match = re.search(r'Description[\s\n]+(.+?)(?=\n(?:Rent|Area|Service Charge|Options|Council|Map|Documents)|$)', 
                                 body_text, re.DOTALL)
            if desc_match:
                return desc_match.group(1).strip()
        except Exception as e:
            self.logger.warning(f"Error extracting description: {e}")
        
        return ""
    
    def _extract_size_sqft(self) -> str:
        """Extract size in square feet from Area field."""
        try:
            # Find the div containing "Area" text
            body_text = self.driver.find_element(By.TAG_NAME, 'body').text
            
            # Look for "Area" followed by numbers
            # Pattern: "Area\n377" or "Area\n377 sq ft"
            area_match = re.search(r'Area[\s\n]+([\d,]+)', body_text)
            if area_match:
                return area_match.group(1).replace(',', '')
            
            # Also try finding "sq ft" pattern anywhere
            sqft_match = re.search(r'([\d,]+)\s*sq\s*ft', body_text, re.IGNORECASE)
            if sqft_match:
                return sqft_match.group(1).replace(',', '')
        except Exception as e:
            self.logger.warning(f"Error extracting size sqft: {e}")
        
        return ""
    
    def _extract_size_acres(self) -> str:
        """Extract size in acres from Land Area field."""
        try:
            body_text = self.driver.find_element(By.TAG_NAME, 'body').text
            
            # Look for "Land Area" or just acres pattern
            land_match = re.search(r'Land Area[\s\n]+([\d.]+)', body_text)
            if land_match:
                return land_match.group(1)
            
            ac_match = re.search(r'([\d.]+)\s*ac(?:res)?', body_text, re.IGNORECASE)
            if ac_match:
                return ac_match.group(1)
        except Exception as e:
            self.logger.warning(f"Error extracting size acres: {e}")
        
        return ""
    
    def _extract_postcode(self) -> str:
        """Extract UK postcode from address."""
        address = self._extract_address()
        # UK postcode pattern
        match = re.search(r'[A-Z]{1,2}\d{1,2}\s?\d[A-Z]{2}', address, re.IGNORECASE)
        if match:
            return match.group(0)
        return ""
    
    def _extract_brochure_url(self) -> str:
        """Extract PDF brochure URL by clicking the brochure button."""
        try:
            # Find the brochure button - user XPath points to property-buttons-component button[3]
            brochure_buttons = self.driver.find_elements(
                By.CSS_SELECTOR,
                "property-buttons-component button"
            )
            
            # Try to find button with "Brochure" text
            brochure_button = None
            for btn in brochure_buttons:
                if 'brochure' in btn.text.lower():
                    brochure_button = btn
                    break
            
            if not brochure_button:
                return ""
            
            # Scroll the button into view to avoid click interception
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", brochure_button)
            time.sleep(1)
            
            # Store current window handle
            original_window = self.driver.current_window_handle
            
            # Use JavaScript click to avoid interception issues
            self.driver.execute_script("arguments[0].click();", brochure_button)
            time.sleep(2)  # Wait for new tab to open
            
            # Get all window handles
            all_windows = self.driver.window_handles
            
            # Switch to the new tab
            for window in all_windows:
                if window != original_window:
                    self.driver.switch_to.window(window)
                    break
            
            # Get the URL from the new tab
            brochure_url = self.driver.current_url
            
            # Close the new tab
            self.driver.close()
            
            # Switch back to the original window
            self.driver.switch_to.window(original_window)
            
            return brochure_url
            
        except Exception as e:
            self.logger.warning(f"Error extracting brochure via button click: {e}")
            # Make sure we're back on the original window
            try:
                self.driver.switch_to.window(self.driver.window_handles[0])
            except:
                pass
            return ""
    
    def _extract_agent_name(self) -> str:
        """Extract agent's name from property-details-agents-component."""
        try:
            # User XPath: /html/body/.../property-details-agents-component/.../h3
            # Find h3 elements that might contain agent names
            agent_component = self.driver.find_elements(By.CSS_SELECTOR, "property-details-agents-component h3")
            
            for h3 in agent_component:
                text = h3.text.strip()
                # Agent names usually contain letters and possibly titles like MRICS
                if text and len(text) > 3:
                    return text
            
            # Fallback: look for text near phone/email
            body_text = self.driver.find_element(By.TAG_NAME, 'body').text
            agent_match = re.search(r'([A-Z][a-z]+ [A-Z][a-z]+(?: [A-Z]+)?)[\s\n]+(?:Managing Director|Director|Agent)', body_text)
            if agent_match:
                return agent_match.group(1)
        except Exception as e:
            self.logger.warning(f"Error extracting agent name: {e}")
        
        return ""
    
    def _extract_agent_city(self) -> str:
        """Extract agent's city."""
        selectors = [".agent-city", "[class*='agent'] .city"]
        return self._safe_find_text(selectors)
    
    def _extract_agent_email(self) -> str:
        """Extract agent's email."""
        try:
            email_link = self.driver.find_element(By.CSS_SELECTOR, "a[href^='mailto:']")
            return email_link.get_attribute('href').replace('mailto:', '')
        except NoSuchElementException:
            return ""
    
    def _extract_agent_phone(self) -> str:
        """Extract agent phone number from property-details-agents-component."""
        try:
            # XPath: /html/body/.../property-details-agents-component/.../a[1]
            # Find all phone links in agent component
            phone_links = self.driver.find_elements(By.CSS_SELECTOR, "property-details-agents-component a[href^='tel:']")
            if phone_links:
                # Get the text of the first phone link
                return phone_links[0].text.strip()
            
            # Fallback: any tel: link
            phone_links_all = self.driver.find_elements(By.CSS_SELECTOR, "a[href^='tel:']")
            if phone_links_all:
                return phone_links_all[0].text.strip()
            
            return ""
        except Exception as e:
            self.logger.warning(f"Error extracting agent phone: {e}")
            return ""
    
    def _extract_agent_street(self) -> str:
        """Extract agent's street address."""
        selectors = [".agent-address", "[class*='agent'] .address"]
        return self._safe_find_text(selectors)
    
    def _extract_agent_postcode(self) -> str:
        """Extract agent's postcode."""
        agent_address = self._extract_agent_street()
        match = re.search(r'[A-Z]{1,2}\d{1,2}\s?\d[A-Z]{2}', agent_address, re.IGNORECASE)
        if match:
            return match.group(0)
        return ""
    
    def _extract_tenure(self) -> str:
        """Extract tenure (Freehold/Leasehold)."""
        selectors = [".tenure", "[class*='tenure']"]
        tenure_text = self._safe_find_text(selectors)
        
        if 'freehold' in tenure_text.lower():
            return "Freehold"
        elif 'leasehold' in tenure_text.lower():
            return "Leasehold"
        
        return ""
    
    def run(self):
        """Main execution method to run the scraper."""
        try:
            self.setup_driver()
            self.navigate_to_homepage()
            
            # Iterate through each dropdown option
            for option in DROPDOWN_OPTIONS:
                self.logger.info(f"\n{'='*60}")
                self.logger.info(f"Processing dropdown option: {option}")
                self.logger.info(f"{'='*60}\n")
                
                # Navigate directly to property type URL
                sale_type = self.navigate_to_property_type(option)
                
                # Load all properties
                property_urls = self.scroll_and_load_all_properties()
                
                # Extract details from each property
                for idx, url in enumerate(property_urls, 1):
                    self.logger.info(f"Processing property {idx}/{len(property_urls)}")
                    
                    data = self.extract_property_details(url, sale_type)
                    
                    if data:
                        self.properties_data.append(data)
                        self.properties_scraped += 1
                    
                    # Delay between requests
                    time.sleep(REQUEST_DELAY)
                
                self.logger.info(f"Completed {option}: {len(property_urls)} properties processed")
            
            # Save all collected data to CSV using the utility function
            if self.properties_data:
                store_data_to_csv(self.properties_data, CSV_FILENAME)
            
            # Final summary
            self.logger.info(f"\n{'='*60}")
            self.logger.info(f"SCRAPING COMPLETE")
            self.logger.info(f"Total properties scraped: {self.properties_scraped}")
            self.logger.info(f"Data saved to: {CSV_FILENAME}")
            self.logger.info(f"{'='*60}\n")
            
            return self.properties_data
            
        except Exception as e:
            self.logger.error(f"Fatal error during scraping: {e}")
            raise
        
        finally:
            if self.driver:
                self.driver.quit()
                self.logger.info("WebDriver closed")


if __name__ == "__main__":
    scraper = KnightCommercialScraper()
    scraper.run()
