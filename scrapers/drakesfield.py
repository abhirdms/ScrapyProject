import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class DrakesfieldScraper:
    BASE_URLS = [
        "https://www.drakesfield.co.uk/residential.html",
        "https://www.drakesfield.co.uk/commercial.html",
    ]
    DOMAIN = "https://www.drakesfield.co.uk"

    def __init__(self):
        self.results = []
        self.seen_blocks = set()

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

        for page_url in self.BASE_URLS:
            self.scrape_page(page_url)

        self.driver.quit()
        return self.results

    # ===================== PAGE ===================== #

    def scrape_page(self, page_url):

        self.driver.get(page_url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'wsb-element-text')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        property_blocks = tree.xpath(
            "//div[contains(@class,'wsb-element-text')]"
            "[.//strong]"
        )

        for block in property_blocks:

            text = self._clean(" ".join(block.xpath(".//text()")))

            # Skip irrelevant blocks
            if not any(k in text.lower() for k in ["let", "sale"]):
                continue
            if "note:" in text.lower():
                continue
            if "now let" in text.lower():
                continue

            unique_key = text[:100]
            if unique_key in self.seen_blocks:
                continue
            self.seen_blocks.add(unique_key)

            obj = self.parse_listing(block, tree, page_url)
            if obj:
                self.results.append(obj)

    # ===================== LISTING ===================== #

    def parse_listing(self, block, tree, page_url):

        text = self._clean(" ".join(block.xpath(".//text()")))

        # ---------- SALE TYPE ---------- #
        sale_type = self.normalize_sale_type(text)

        # ---------- PROPERTY TYPE ---------- #
        property_sub_type = self._clean(" ".join(
            block.xpath(".//strong[contains(.,'SHOP') or contains(.,'Bedroom')]/text()")
        ))

        # ---------- ADDRESS ---------- #
        display_address = self._clean(" ".join(
            block.xpath(".//em[not(.//a)]//text()")
        ))

        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(text, sale_type)

        # ---------- IMAGES (nearest previous gallery) ---------- #
        gallery = block.xpath(
            "preceding::div[contains(@class,'wsb-element-gallery')][1]"
        )

        property_images = []
        if gallery:
            property_images = gallery[0].xpath(".//img/@src")

        # ---------- BROCHURE / PDF ---------- #
        brochure_urls = block.xpath(".//a[contains(@href,'nebula')]/@href")

        obj = {
            "listingUrl": page_url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": text,
            "sizeFt": "",
            "sizeAc": "",
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Drakesfield",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": self.extract_tenure(text),
            "saleType": sale_type,
        }

        return obj

    # ===================== HELPERS ===================== #

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale":
            return ""

        if not text:
            return ""

        t = text.lower()

        if any(k in t for k in [
            "poa", "price on application", "upon application", "on application"
        ]):
            return ""

        if any(k in t for k in [
            "per annum", "pa", "per year", "pcm",
            "per month", "pw", "per week", "rent"
        ]):
            return ""

        m = re.search(r'[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?', t)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))
        if "m" in m.group(0):
            num *= 1_000_000

        return str(int(num))

    def extract_tenure(self, text):
        if not text:
            return ""

        t = text.lower()
        if "freehold" in t:
            return "Freehold"
        if "leasehold" in t:
            return "Leasehold"
        return ""

    def extract_postcode(self, text: str):
        if not text:
            return ""

        text = text.upper()

        full_pattern = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        partial_pattern = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        match = re.search(full_pattern, text)
        if match:
            return match.group().strip()

        match = re.search(partial_pattern, text)
        return match.group().strip() if match else ""

    def normalize_sale_type(self, text):
        t = text.lower()
        if "for sale" in t:
            return "For Sale"
        if "let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""