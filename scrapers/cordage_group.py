import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class CordageGroupScraper:
    BASE_URL = "https://www.cordagegroup.co.uk/development-opportunities"
    DOMAIN = "https://www.cordagegroup.co.uk"

    def __init__(self):
        self.results = []
        self.seen_addresses = set()

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
            "//section[@data-test='page-section']"
        )))

        tree = html.fromstring(self.driver.page_source)

        # Each property is its own section containing <h2><strong>Location</strong></h2>
        sections = tree.xpath("//section[.//h2//strong]")

        for section in sections:
            obj = self.parse_section(section)
            if obj:
                self.results.append(obj)

        self.driver.quit()
        return self.results

    # ===================== SECTION PARSER ===================== #

    def parse_section(self, section):

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            section.xpath(".//h2//strong/text()")
        ))

        if not display_address:
            return None

        if display_address in self.seen_addresses:
            return None

        self.seen_addresses.add(display_address)

        # ---------- DESCRIPTION ---------- #
        description_parts = section.xpath(
            ".//div[contains(@class,'sqs-html-content')]//p//text()"
        )

        detailed_description = self._clean(" ".join(description_parts))

        # ---------- IMAGES ---------- #
        property_images = section.xpath(
            ".//img[@data-sqsp-image-block-image]/@src"
        )

        # ---------- SALE TYPE ---------- #
        sale_type = "For Sale"

        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(detailed_description)

        obj = {
            "listingUrl": self.BASE_URL,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "Development Opportunity",
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": [],
            "agentCompanyName": "Cordage Group",
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

        text = text.lower().replace(",", "")
        text = text.replace("m²", "sqm")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        # ---- SQ FT ---- #
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\.?\s*ft|sqft|sf)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        # ---- SQM → SQFT ---- #
        if not size_ft:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sqm|m2)',
                text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm = min(a, b) if b else a
                size_ft = round(sqm * 10.7639, 3)

        # ---- ACRES ---- #
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text):
        if not text:
            return ""

        t = text.lower()

        if any(k in t for k in [
            "poa", "price on application", "upon application", "on application"
        ]):
            return ""

        m = re.search(r'£\s*(\d+(?:,\d{3})*(?:\.\d+)?)(\s*m|\s*k)?', t)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))

        if m.group(2):
            if "m" in m.group(2):
                num *= 1_000_000
            if "k" in m.group(2):
                num *= 1_000

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

    def _clean(self, val):
        return " ".join(val.split()) if val else ""