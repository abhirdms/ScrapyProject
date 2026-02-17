    
import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class JHWalterScraper:

    BASE_URLS = {
        "Residential Sale": "https://www.brown-co.com/services/residential/property-search",
        "Residential Let": "https://www.brown-co.com/services/residential/property-search?type=let",
        "Development": "https://www.brown-co.com/services/development/land-search",
        "Commercial": "https://www.brown-co.com/services/commercial/property-search",
        "Rural": "https://www.brown-co.com/services/rural/property-search",
        "International Property": "https://www.brown-co.com/services/international/property",
        "International Land": "https://www.brown-co.com/services/international/land-farms",
    }

    DOMAIN = "https://www.brown-co.com"

    def __init__(self):
        self.results = []
        self.seen_urls = set()

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")

        service = Service("/usr/bin/chromedriver")
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 20)

    # ===================== RUN ===================== #

    def run(self):

        for label, base_url in self.BASE_URLS.items():

            page = 1

            while True:
                page_url = base_url if page == 1 else f"{base_url}?page={page}"
                self.driver.get(page_url)

                try:
                    self.wait.until(EC.presence_of_element_located((
                        By.XPATH,
                        "//div[contains(@class,'card--property-listing')]"
                    )))
                except Exception:
                    break

                tree = html.fromstring(self.driver.page_source)

                listing_urls = tree.xpath(
                    "//div[contains(@class,'card--property-listing')]"
                    "//a[contains(@class,'cp-link')]/@href"
                )

                if not listing_urls:
                    break

                new_links_found = False

                for href in listing_urls:
                    url = urljoin(self.DOMAIN, href)

                    if url in self.seen_urls:
                        continue

                    new_links_found = True
                    self.seen_urls.add(url)

                    try:
                        obj = self.parse_listing(url)
                        if obj:
                            self.results.append(obj)
                    except Exception:
                        continue

                # STOP if no new unique listings
                if not new_links_found:
                    break

                page += 1

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url):

        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'card--property--view')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        display_address = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'cp-loc')]//text()")
        ))

        property_sub_type = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'cp-desc')]//text()")
        ))

        detailed_description = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'pv-about')]//text()")
        ))

        raw_price = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'cp-price')]//text()")
        ))

        sale_type = self.detect_sale_type(detailed_description, raw_price)

        price = self.extract_numeric_price(
            f"{raw_price} {detailed_description}",
            sale_type
        )

        size_text = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'cp-key-item')]//text()")
        ))

        size_ft, size_ac = self.extract_size(size_text)

        property_images = list(dict.fromkeys(
            tree.xpath(
                "//div[contains(@class,'pv-slide')]"
                "//div[contains(@class,'pv-image')]//a/@href"
            )
        ))

        brochure_urls = tree.xpath(
            "//div[contains(@class,'cp-brochure-download')]//a/@href"
        )

        agent_name = self._clean(" ".join(
            tree.xpath(
                "(//div[contains(@class,'card--contact')]"
                "//div[contains(@class,'contact-name')]//text())[1]"
            )
        ))

        agent_phone = self._clean(" ".join(
            tree.xpath(
                "(//div[contains(@class,'card--contact')]"
                "//a[contains(@href,'tel:')]/text())[1]"
            )
        ))

        tenure = self.extract_tenure(detailed_description)

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Brown & Co",
            "agentName": agent_name,
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": agent_phone,
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }
        return obj

    # ===================== HELPERS ===================== #

    def detect_sale_type(self, description, price_text):

        text = f"{description} {price_text}".lower()

        # STRICT To Let detection
        if re.search(r'\bto let\b|\bfor rent\b|\bpcm\b|\bper month\b|\bper week\b|\bpw\b|\bper annum\b', text):
            return "To Let"

        # Explicit Sale indicators
        if re.search(r'\bfor sale\b|\bguide price\b|\boffers in excess\b', text):
            return "For Sale"

        # If price exists and no rent wording → assume sale
        if "£" in text and not re.search(r'\bpcm\b|\bper month\b|\bper week\b|\bper annum\b|\brent\b', text):
            return "For Sale"

        return ""

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ac = ""

        m = re.search(r'\(([\d.]+)\s*ac\)', text)
        if m:
            size_ac = float(m.group(1))
        else:
            m2 = re.search(r'(\d+(?:\.\d+)?)\s*ha', text)
            if m2:
                hectares = float(m2.group(1))
                size_ac = round(hectares * 2.47105, 3)

        return "", size_ac

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale":
            return ""

        t = text.lower()

        if re.search(r'\bpoa\b|price on application|upon application|subject to contract', t):
            return ""

        if re.search(r'\bpcm\b|\bper month\b|\bper week\b|\bper annum\b|\brent\b', t):
            return ""

        m = re.search(r'[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?', t)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))
        if "m" in m.group(0):
            num *= 1_000_000

        return str(int(num))

    def extract_tenure(self, text):
        t = text.lower()
        if "freehold" in t:
            return "Freehold"
        if "leasehold" in t:
            return "Leasehold"
        return ""

    def extract_postcode(self, text):
        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'
        t = text.upper()
        m = re.search(FULL, t) or re.search(PARTIAL, t)
        return m.group() if m else ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
