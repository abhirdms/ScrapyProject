import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class DunitzCoScraper:
    BASE_URL = "https://dunitzandco.com/current-sales"
    DOMAIN = "https://dunitzandco.com"

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
            "//ul[contains(@class,'user-items-list-item-container')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_blocks = tree.xpath(
            "//ul[contains(@class,'user-items-list-item-container')]"
            "/li[contains(@class,'list-item')]"
        )

        for block in listing_blocks:
            try:
                obj = self.parse_listing(block)
                if obj:
                    self.results.append(obj)
            except Exception:
                continue

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, block):

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            block.xpath(".//h2[contains(@class,'list-item-content__title')]/text()")
        ))

        # ---------- DESCRIPTION ---------- #
        description = self._clean(" ".join(
            block.xpath(
                ".//div[contains(@class,'list-item-content__description')]"
                "//text()[not(ancestor::a)]"
            )
        ))

        # ---------- SALE TYPE ---------- #
        status_raw = self._clean(" ".join(
            block.xpath(".//strong/text()")
        ))

        sale_type = self.normalize_sale_type(status_raw)
        if sale_type == "Sold":
            return None

        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type_raw = self._clean(" ".join(
            block.xpath(".//p[contains(text(),'Sector')]/text()")
        ))

        property_sub_type = ""
        if "Sector" in property_sub_type_raw:
            property_sub_type = property_sub_type_raw.split("Sector -")[-1].strip()

        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(description)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(description)

        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(description, sale_type)

        # ---------- IMAGE ---------- #
        property_images = block.xpath(
            ".//div[contains(@class,'list-item-media')]//img/@src"
        )

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in block.xpath(
                ".//a[contains(text(),'Download PDF')]/@href"
            )
        ]

        # If no detail page → use brochure as listingUrl
        listing_url = brochure_urls[0] if brochure_urls else ""

        if listing_url in self.seen_urls:
            return None
        self.seen_urls.add(listing_url)

        obj = {
            "listingUrl": listing_url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Dunitz & Co",
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
        text = text.replace("ft²", "sq ft")
        text = text.replace("m²", "sqm")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        # SQ FT
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft|sqft|sf|square\s*feet)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        # SQM → convert
        if not size_ft:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(sqm|sq\.?\s*m|m2)',
                text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm_value = min(a, b) if b else a
                size_ft = round(sqm_value * 10.7639, 3)

        # ACRES
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        # HECTARES → convert
        if not size_ac:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(hectares?|ha)',
                text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                hectare_value = min(a, b) if b else a
                size_ac = round(hectare_value * 2.47105, 3)

        return size_ft, size_ac

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

        m = re.search(r'[£]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?', text)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))
        if "m" in m.group(0).lower():
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

    def extract_postcode(self, text):
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
        if "sale" in t or "for sale" in t:
            return "For Sale"
        
        if "rent" in t or "to let" in t:
            return "To Let"
        if "sold" in t:
            return "Sold"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""