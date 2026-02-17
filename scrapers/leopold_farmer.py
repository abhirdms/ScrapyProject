import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class LeopoldFarmerScraper:
    BASE_URLS = [
        "https://www.leopoldfarmer.com/offices.htm",
        "https://www.leopoldfarmer.com/properties.htm",
    ]
    DOMAIN = "https://www.leopoldfarmer.com"

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
        for page_url in self.BASE_URLS:
            self.driver.get(page_url)

            self.wait.until(EC.presence_of_element_located((
                By.XPATH, "//a[@name]"
            )))

            tree = html.fromstring(self.driver.page_source)

            anchors = tree.xpath("//a[@name]/@name")

            for anchor in anchors:
                if anchor.lower() == "top":
                    continue

                listing_url = f"{page_url}#{anchor}"

                if listing_url in self.seen_urls:
                    continue
                self.seen_urls.add(listing_url)

                try:
                    obj = self.parse_listing(tree, anchor, listing_url)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, tree, anchor, listing_url):

        section = tree.xpath(f"//a[@name='{anchor}']/ancestor::table[1]")
        if not section:
            return None

        section = section[0]

        raw_text = self._clean(" ".join(
            section.xpath(".//text()[normalize-space()]")
        ))

        if not raw_text:
            return None

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            section.xpath(".//b//text()")
        ))

        # ---------- SALE TYPE ---------- #
        sale_type = self.normalize_sale_type(raw_text)

        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(raw_text)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(raw_text)

        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(raw_text, sale_type)

        # ---------- IMAGES ---------- #
        property_images = [
            urljoin(self.DOMAIN, src)
            for src in section.xpath(".//img/@src")
            if src and not src.lower().endswith(("logo.gif", "bullet.gif"))
        ]

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in section.xpath(".//a[contains(@href,'.pdf')]/@href")
        ]

        obj = {
            "listingUrl": listing_url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": property_images,
            "detailedDescription": raw_text,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(raw_text),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Leopold Farmer",
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
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(r'(\d+(?:\.\d+)?)\s*(sq\s*ft|sqft|sq\.ft)', text)
        if m:
            size_ft = round(float(m.group(1)), 3)

        m = re.search(r'(\d+(?:\.\d+)?)\s*(acres?|acre|ac)', text)
        if m:
            size_ac = round(float(m.group(1)), 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if not text:
            return ""

        t = text.lower()

        if any(k in t for k in [
            "poa", "price on application", "upon application"
        ]):
            return ""

        m = re.search(r'[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?', text)
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

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        t = text.upper()
        m = re.search(FULL, t) or re.search(PARTIAL, t)
        return m.group() if m else ""

    def normalize_sale_type(self, text):
        t = text.lower()

        if "to let" in t or "rent" in t:
            return "To Let"

        if "sold" in t or "freehold" in t or "for sale" in t:
            return "For Sale"

        if "lease assigned" in t:
            return "For Sale"

        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
