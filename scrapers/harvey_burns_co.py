import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class HarveyBurnsCoScraper:
    BASE_URL = "https://harveyburns.com/"
    DOMAIN = "https://harveyburns.com/"

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
        print(f"Fetching: {self.BASE_URL}")
        self.driver.get(self.BASE_URL)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH, "//section[@class='listing-layout']//article[@class='property-item clearfix']"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            "//section[@class='listing-layout']"
            "//article[@class='property-item clearfix']//h4/a/@href"
        )

        for url in listing_urls:
            try:
                self.results.append(self.parse_listing(url))
            except Exception:
                continue

        self.driver.quit()
        return self.results

    # ================= LISTING ================= #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH, "//div[contains(@id,'property-detail')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- BASIC FIELDS ---------- #

        display_address = self._clean(" ".join(
            tree.xpath("//div[@class='wrap clearfix']/h1[@class='page-title']/span/text()")
        ))

        detailed_description = self._clean(" ".join(
            tree.xpath("//article[@class='property-item clearfix']//div[@class='content clearfix']/p//text()")
        ))

        sale_type_raw = self._clean(" ".join(
            tree.xpath("//h5[@class='price']//span[@class='status-label']/text()")
        ))

        property_sub_type = self._clean(" ".join(
            tree.xpath("//span/small/text()")
        ))

        # ---------- SIZE (FROM DESCRIPTION ONLY) ---------- #

        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- IMAGES ---------- #

        property_images = tree.xpath(
            "//div[@id='property-detail-flexslider']"
            "//ul[@class='slides']//li//a/img/@src"
        )

        # ---------- BROCHURE ---------- #

        brochure = tree.xpath(
            "//ul[@class='attachments-list clearfix']"
            "//li[contains(@class,'pdf')]/a/@href"
        )

        # ---------- OBJECT ---------- #

        obj = {
            "listingUrl": url,

            "displayAddress": display_address,

            "price": self.extract_numeric_price(detailed_description, sale_type_raw),

            "propertySubType": property_sub_type,

            "propertyImage": property_images,

            "detailedDescription": detailed_description,

            "sizeFt": size_ft,
            "sizeAc": size_ac,

            "postalCode": self.extract_postcode(display_address),

            "brochureUrl": self.normalize_url(brochure[0]) if brochure else "",

            "agentCompanyName": "Harvey Burns & Co",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",

            "tenure": "",

            "saleType": self.normalize_sale_type(sale_type_raw),
        }
        print("*"*20)
        print(obj)
        print("*"*20)

        return obj

    # ================= HELPERS ================= #

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        sqft_pattern = (
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\s*ft|sqft|sf)'
        )
        m = re.search(sqft_pattern, text)
        if m:
            start = float(m.group(1))
            end = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(start, end), 3) if end else round(start, 3)

        acre_pattern = (
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac)'
        )
        m = re.search(acre_pattern, text)
        if m:
            start = float(m.group(1))
            end = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(start, end), 3) if end else round(start, 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if not text or "sale" not in sale_type.lower():
            return ""

        raw = text.lower()
        if any(k in raw for k in ["poa", "application"]):
            return ""

        raw = raw.replace("£", "").replace(",", "")
        nums = re.findall(r"\d+(?:\.\d+)?", raw)
        return str(int(float(nums[0]))) if nums else ""

    def extract_postcode(self, text):
        if not text:
            return ""

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        text = text.upper()
        m = re.search(FULL, text) or re.search(PARTIAL, text)
        return m.group() if m else ""

    def normalize_sale_type(self, text):
        t = text.lower()
        if "sale" in t:
            return "For Sale"
        if "let" in t:
            return "To Let"
        if "under offer" in t:
            return "Under Offer"
        return ""

    def normalize_url(self, url):
        return urljoin(self.DOMAIN, url) if url else ""

    def _clean(self, val):
        return val.strip() if val else ""
