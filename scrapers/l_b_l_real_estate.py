import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class LBLRealEstateScraper:
    BASE_URL = "https://www.lblrealestate.co.uk/available-properties.php"
    DOMAIN = "https://www.lblrealestate.co.uk"

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
            "//div[contains(@class,'single-services')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listings = tree.xpath("//div[contains(@class,'single-services')]")

        for node in listings:
            obj = self.parse_listing(node)
            if not obj:
                continue

            if obj["listingUrl"] in self.seen_urls:
                continue

            self.seen_urls.add(obj["listingUrl"])
            self.results.append(obj)

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, node):

        display_address = self._clean(" ".join(
            node.xpath(".//div[contains(@class,'services-content')]/p[1]/text()")
        ))


        sale_type_raw = self._clean(" ".join(
            node.xpath(".//div[contains(@class,'services-content')]/small/text()")
        ))

        property_sub_type = self._clean(" ".join(
            node.xpath(".//div[contains(@class,'services-thumb')]/p/text()")
        ))

        image = node.xpath(".//div[contains(@class,'services-thumb')]//img/@src")
        property_image = image[0] if image else ""

        brochure = node.xpath(
            ".//a[contains(text(),'Download Brochure')]/@href"
        )
        brochure_url = urljoin(self.DOMAIN, brochure[0]) if brochure else ""

        # brochure used as listingUrl
        listing_url = brochure_url

        # ---------- PRICE ---------- #
        price_text = self._clean(" ".join(
            node.xpath(".//li[span[contains(text(),'Price')]]/text()")
        ))

        sale_type = self.normalize_sale_type(sale_type_raw)
        price = self.extract_numeric_price(price_text, sale_type)

        # ---------- SIZE ---------- #
        area_text = self._clean(" ".join(
            node.xpath(".//li[span[contains(text(),'Area')]]/text()")
        ))

        size_ft, size_ac = self.extract_size(area_text)

        # ---------- TENURE (from property type text) ---------- #
        tenure = self.extract_tenure(property_sub_type)

        obj = {
            "listingUrl": listing_url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_image,
            "detailedDescription": "",
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": [brochure_url] if brochure_url else [],
            "agentCompanyName": "LBL Real Estate",
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

        t = text.lower().replace(",", "")
        t = re.sub(r"[–—−]", "-", t)

        size_ft = ""
        size_ac = ""

        # sq ft
        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\s*ft)', t)
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = str(int(min(a, b))) if b else str(int(a))

        # acres
        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac)', t)
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = str(min(a, b)) if b else str(a)

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale":
            return ""

        if not text:
            return ""

        t = text.lower()

        if any(x in t for x in [
            "poa", "price on application", "upon application", "on application"
        ]):
            return ""

        if any(x in t for x in [
            "per annum", "pa", "per year", "pcm", "per month", "pw", "rent"
        ]):
            return ""

        m = re.search(r'£\s*(\d+(?:,\d{3})*(?:\.\d+)?)', t)
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
        if "to let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
