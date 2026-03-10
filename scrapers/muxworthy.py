import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class MuxworthyScraper:
    BASE_URL = "http://www.muxworthyllp.com/coastal.php"
    DOMAIN = "http://www.muxworthyllp.com"

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

    # ===================== RUN ===================== #

    def run(self):
        self.driver.get(self.BASE_URL)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[@id='content']"
        )))

        tree = html.fromstring(self.driver.page_source)

        listings = tree.xpath("//div[@id='content']")

        for listing in listings:
            try:
                obj = self.parse_listing(listing)
                if obj:
                    self.results.append(obj)
            except Exception:
                continue

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, listing):

        # ---------- TITLE ---------- #
        display_address = self._clean(" ".join(
            listing.xpath(".//div[@id='contentlandscape']/h1/text()")
        ))

        # ---------- DESCRIPTION ---------- #
        desc_parts = listing.xpath(
            ".//div[@id='contentlandscape']/p//text()"
        )

        detailed_description = self._clean(" ".join(desc_parts))

        # ---------- IMAGES ---------- #
        property_images = [
            urljoin(self.DOMAIN, src)
            for src in listing.xpath(".//div[@id='movielandscape']//img/@src")
            if src
        ]

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in listing.xpath(".//a[contains(@href,'.pdf')]/@href")
        ]

        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(detailed_description)

        sale_type = self.normalize_sale_type(detailed_description)

        # ---------- POSTCODE ---------- #
        postal_code = self.extract_postcode(detailed_description)

        obj = {
            "listingUrl": brochure_urls[0],
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": postal_code,
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Muxworthy",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }


        return obj

    # ===================== HELPERS ===================== #

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower()
        text = text.replace(",", "")

        size_ft = ""
        size_ac = ""

        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:sq\s*ft|square\s*feet)', text)
        if m:
            size_ft = m.group(1)

        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:acre|acres)', text)
        if m:
            size_ac = m.group(1)

        return size_ft, size_ac
    
    def normalize_sale_type(self, text):
        t = text.lower()
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""

    def extract_numeric_price(self, text):
        if not text:
            return ""

        m = re.search(r'[£]\s*(\d+(?:,\d{3})*(?:\.\d+)?)', text)
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

        text = text.upper()

        pattern = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        match = re.search(pattern, text)

        return match.group().strip() if match else ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""