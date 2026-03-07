import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class NJWEScraper:

    BASE_URL = "https://www.njwe.co.uk/properties.html"
    DOMAIN = "https://www.njwe.co.uk"

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
            "//h2[contains(@class,'wsite-content-title')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        property_blocks = tree.xpath(
            "//h2[contains(@class,'wsite-content-title')]/ancestor::div[contains(@class,'wsite-section-wrap')]"
        )

        for block in property_blocks:
            try:
                obj = self.parse_listing(block)
                if obj:
                    self.results.append(obj)
            except Exception:
                continue

        self.driver.quit()

        return self.results

    # ===================== PARSE PROPERTY ===================== #

    def parse_listing(self, block):

        # ---------- TITLE / ADDRESS ---------- #

        display_address = self._clean(" ".join(
            block.xpath(".//h2[contains(@class,'wsite-content-title')]//text()")
        ))

        # ---------- DESCRIPTION ---------- #

        detailed_description = self._clean(" ".join(
            block.xpath(".//div[contains(@class,'paragraph')]//text()")
        ))

        # ---------- IMAGES ---------- #

        images = [
            urljoin(self.DOMAIN, src)
            for src in block.xpath(".//img/@src")
        ]

        # ---------- BROCHURE ---------- #

        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in block.xpath(".//a[contains(@href,'.pdf')]/@href")
        ]

        # ---------- SALE TYPE ---------- #

        sale_type = self.normalize_sale_type(display_address)

        # ---------- SIZE ---------- #

        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- PRICE ---------- #

        price = self.extract_numeric_price(detailed_description)

        obj = {
            "listingUrl": self.BASE_URL,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "NJWE",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": "",
            "saleType": sale_type,
        }

        print("*****" * 10)
        print(obj)
        print("*****" * 10)

        return obj

    # ===================== HELPERS ===================== #

    def normalize_sale_type(self, text):

        text = text.lower()

        if "sold" in text:
            return "Sold"

        if "let" in text:
            return "To Let"

        if "lease assignment" in text:
            return "To Let"

        if "investment" in text:
            return "For Sale"

        return ""

    def extract_numeric_price(self, text):

        if not text:
            return ""

        m = re.search(r'£\s*(\d+(?:,\d{3})*)', text)

        if m:
            return float(m.group(1).replace(",", ""))

        return ""

    def extract_size(self, text):

        if not text:
            return "", ""

        text = text.lower().replace(",", "")

        size_ft = ""
        size_ac = ""

        m = re.search(r'(\d+(?:\.\d+)?)\s*(sq\s*ft|sqft)', text)

        if m:
            size_ft = float(m.group(1))

        m = re.search(r'(\d+(?:\.\d+)?)\s*(acre|acres)', text)

        if m:
            size_ac = float(m.group(1))

        return size_ft, size_ac

    def extract_postcode(self, text):

        m = re.search(
            r'[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}',
            text,
            re.I
        )

        return m.group(0).upper() if m else ""

    def _clean(self, text):

        return re.sub(r"\s+", " ", text).strip()


if __name__ == "__main__":

    scraper = NJWEScraper()

    data = scraper.run()

    print(len(data))