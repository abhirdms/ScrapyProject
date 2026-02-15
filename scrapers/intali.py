import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class IntaliScraperAbhi:
    BASE_URL = "https://intali.com/future-opportunities/"
    DOMAIN = "https://intali.com"

    def __init__(self):
        self.results = []
        self.seen_urls = set()

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        service = Service("/usr/bin/chromedriver")
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 20)

    # ===================== RUN ===================== #

    def run(self):

        self.driver.get(self.BASE_URL)

        try:
            self.wait.until(EC.presence_of_element_located((
                By.XPATH,
                "//div[@data-elementor-type='wp-post']"
            )))
        except Exception:
            self.driver.quit()
            return []

        tree = html.fromstring(self.driver.page_source)

        sections = tree.xpath(
            "//div[@data-elementor-type='wp-post']"
            "//section[contains(@class,'elementor-section-stretched')]"
        )

        for index, section in enumerate(sections, start=1):

            listing_url = f"{self.BASE_URL}#opportunity-{index}"

            if listing_url in self.seen_urls:
                continue
            self.seen_urls.add(listing_url)

            try:
                obj = self.parse_listing(section, listing_url)
                if obj:
                    self.results.append(obj)
            except Exception:
                continue

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, section, listing_url):

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            section.xpath(".//h2/text()")
        ))

        if not display_address:
            return None

        # ---------- DETAILED DESCRIPTION ---------- #
        detailed_description = self._clean(" ".join(
            section.xpath(
                ".//div[contains(@class,'elementor-widget-text-editor')]"
                "//p[not(.//strong)]//text()"
            )
        ))

        # ---------- PRICE ---------- #
        price_text = self._clean(" ".join(
            section.xpath(
                ".//div[contains(@class,'elementor-widget-text-editor')]//strong//text()"
            )
        ))

        price = self.extract_numeric_price(price_text, "")

        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- IMAGES ---------- #
        property_images = [
            src for src in section.xpath(
                ".//div[contains(@class,'elementor-widget-image')]//img/@src"
            ) if src
        ]

        obj = {
            "listingUrl": listing_url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": "",
            "brochureUrl": [],
            "agentCompanyName": "Intali",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": "",
            "saleType": "",
        }

        return obj

    # ===================== HELPERS ===================== #

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        # Acres
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac)\b',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        # Sq Ft
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\.?\s*ft\.?|sqft|sf)\b',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if not text:
            return ""

        raw = text.lower().replace(",", "")

        if "poa" in raw:
            return ""

        m = re.search(r'£\s*(\d+(?:\.\d+)?)', raw)
        if not m:
            return ""

        return m.group(1)

    def extract_tenure(self, text):
        if not text:
            return ""

        t = text.lower()
        if "freehold" in t:
            return "Freehold"
        if "leasehold" in t:
            return "Leasehold"
        return ""

    def extract_postcode(self, text):
        if not text:
            return ""

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        t = text.upper()
        m = re.search(FULL, t) or re.search(PARTIAL, t)
        return m.group() if m else ""

    def normalize_sale_type(self, text):
        t = text.lower()
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
