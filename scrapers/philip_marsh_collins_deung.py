import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class PmcdScraperaashishgiri:
    BASE_URL = "https://www.pmcd.co.uk/property-search/"
    DOMAIN = "https://www.pmcd.co.uk/"

    def __init__(self):
        self.results = []

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        service = Service("/usr/bin/chromedriver")

        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 20)

    # ---------------- RUN ---------------- #

    def run(self):
        self.driver.get(self.BASE_URL)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//article[contains(@class,'property')]//h3/a"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            "//article[contains(@class,'property')]//h3/a/@href"
        )

        for rel_url in listing_urls:
            try:
                url = urljoin(self.DOMAIN, rel_url)
                self.results.append(self.parse_listing(url))
            except Exception:
                continue

        self.driver.quit()
        return self.results

    # ---------------- LISTING ---------------- #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h1[@class='entry-title']"
        )))

        tree = html.fromstring(self.driver.page_source)

        display_address = self._clean(" ".join(
            tree.xpath("//h1[@class='entry-title']/text()")
        ))

        subtitle_text = self._clean(" ".join(
            tree.xpath("//h2[@class='entry-subtitle']/text()")
        ))

        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'entry-content')]//p"
                "[not(ancestor::div[contains(@class,'brookly-hatom-data')])]//text()"
            )
        ))

        property_details_text = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'property-details')]//p//text()")
        ))

        size_ft, size_ac = self.extract_size(property_details_text)

        obj = {
            "listingUrl": url,

            "displayAddress": display_address,

            "price": self.extract_numeric_price(detailed_description, "For Sale"),

            "propertySubType": property_details_text,

            "propertyImage": [
                urljoin(self.DOMAIN, img)
                for img in tree.xpath(
                    "//div[@class='entry-thumbnail']//img/@src"
                )
            ],

            "detailedDescription": detailed_description,

            "sizeFt": size_ft,
            "sizeAc": size_ac,

            "postalCode": self.extract_postcode(subtitle_text),

            "brochureUrl": [
                urljoin(self.DOMAIN, u)
                for u in tree.xpath(
                    "//div[@class='entry-brochure clearfix']//a/@href"
                )
            ],

            "agentCompanyName": "Philip Marsh Collins Deung",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",

            "tenure": self.get_tenure_from_description(property_details_text),

            "saleType": "",
        }

        return obj

    # ---------------- HELPERS ---------------- #

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")

        size_ft = ""
        size_ac = ""

        sqft = re.search(r'(\d+(?:\.\d+)?)\s*(sq\s*ft|sqft|ft2|ft²)', text)
        if sqft:
            size_ft = int(float(sqft.group(1)))

        sqm = re.search(r'(\d+(?:\.\d+)?)\s*(m2|sqm|m²)', text)
        if sqm and not size_ft:
            size_ft = int(float(sqm.group(1)) * 10.7639)

        acres = re.search(r'(\d+(?:\.\d+)?)\s*(acres?|acre|ac)', text)
        if acres:
            size_ac = round(float(acres.group(1)), 3)

        return size_ft, size_ac

    def extract_postcode(self, text):
        if not text:
            return ""

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        text = text.upper()
        m = re.search(FULL, text) or re.search(PARTIAL, text)
        return m.group().strip() if m else ""

    def extract_numeric_price(self, text, sale_type):
        if not text:
            return ""

        raw = text.lower()

        if any(k in raw for k in [
            "poa",
            "price on application",
            "on application",
            "subject to contract"
        ]):
            return ""

        raw = raw.replace("£", "").replace(",", "")
        raw = re.sub(r"(to|–|—)", "-", raw)

        numbers = re.findall(r"\d+(?:\.\d+)?", raw)
        if not numbers:
            return ""

        price = min(float(n) for n in numbers)
        return str(int(price)) if price.is_integer() else str(price)

    def get_tenure_from_description(self, text):
        if not text:
            return ""

        t = text.lower()

        if "freehold" in t:
            return "Freehold"
        if "leasehold" in t or "lease" in t:
            return "Leasehold"

        return ""

    def _clean(self, val):
        return val.strip() if val else ""
