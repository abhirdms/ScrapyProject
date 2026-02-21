import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class RandSurveyorsScraper:
    BASE_URL = "https://www.rand-surveyors.co.uk/properties"
    DOMAIN = "https://www.rand-surveyors.co.uk"

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

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[@role='listitem']"
        )))

        tree = html.fromstring(self.driver.page_source)

        listings = tree.xpath("//div[@role='listitem']")

        for item in listings:
            try:
                obj = self.parse_listing(item)
                if obj:
                    self.results.append(obj)
            except Exception:
                continue

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, item):

        # ---------- TITLE ---------- #
        property_sub_type = self._clean(" ".join(
            item.xpath(".//h2//text()")
        ))

        # ---------- SIZE ---------- #
        size_text = self._clean(" ".join(
            item.xpath(".//p[.//span[contains(text(),'sq')]]//text()")
        ))

        # ---------- ADDRESS ---------- #
        display_address = self._clean(" ".join(
            item.xpath(".//p[contains(text(),'United Kingdom') or contains(text(),'UK')]//text()")
        ))

        # ---------- PRICE ---------- #
        price_text = self._clean(" ".join(
            item.xpath(".//p[contains(text(),'£')]//text()")
        ))

        # ---------- IMAGE ---------- #
        property_images = item.xpath(".//img/@src")

        # ---------- BROCHURE (USED AS LISTING URL) ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in item.xpath(".//a[contains(@href,'.pdf')]/@href")
        ]

        listing_url = brochure_urls[0] if brochure_urls else ""

        # ---------- SALE TYPE ---------- #
        sale_type = self.normalize_sale_type(price_text)

        # ---------- DESCRIPTION ---------- #
        detailed_description = " ".join(
            part for part in [
                property_sub_type,
                size_text,
                display_address,
                price_text
            ] if part
        )

        # ---------- SIZE EXTRACTION ---------- #
        size_ft, size_ac = self.extract_size(size_text)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- PRICE NUMERIC (ONLY IF FOR SALE) ---------- #
        price = self.extract_numeric_price(price_text, sale_type)

        obj = {
            "listingUrl": listing_url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Rand Surveyors",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }

        print("*****" * 10)
        print(obj)
        print("*****" * 10)

        return obj

    # ===================== HELPERS ===================== #

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\.?\s*ft|sqft|sf)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale":
            return ""

        if not text:
            return ""

        t = text.lower()

        if "roa" in t or "poa" in t:
            return ""

        m = re.search(r'£\s*(\d+(?:,\d{3})*)', text)
        if not m:
            return ""

        return m.group(1).replace(",", "")

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
        if "rent" in t or "pa" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""