import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class InglebyTriceScraperAbhi:
    BASE_URL = "https://inglebytrice.co.uk/conventional-properties/"
    DOMAIN = "https://inglebytrice.co.uk"

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

        # Handle Load More button
        while True:
            try:
                btn = self.driver.find_element(By.ID, "load_more")
                self.driver.execute_script("arguments[0].click();", btn)
                self.driver.implicitly_wait(2)
            except Exception:
                break

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//a[contains(@class,'view-btn')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath("//a[contains(@class,'view-btn')]/@href")

        for href in listing_urls:
            url = urljoin(self.DOMAIN, href)

            if url in self.seen_urls:
                continue

            self.seen_urls.add(url)

            try:
                obj = self.parse_listing(url)
                if obj:
                    self.results.append(obj)
            except Exception:
                continue

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url):

        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'property-single-heading')]/h1"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        address_1 = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'property-single-heading')]/h1/text()")
        ))

        address_2 = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'property-single-heading')]/h5/text()")
        ))

        display_address = f"{address_1} {address_2}".strip()

        # ---------- SALE TYPE ---------- #
        sale_type_raw = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'property-single-heading')]//span/text()")
        ))

        sale_type = self.normalize_sale_type(sale_type_raw)

        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type = ""

        # ---------- DESCRIPTION ---------- #
        details_text = tree.xpath(
            "//section[contains(@class,'property-single-content-sec')]"
            "//h3[normalize-space()='Details']/following-sibling::p//text()"
        )

        spec_text = tree.xpath(
            "//section[contains(@class,'property-single-content-sec')]"
            "//div[contains(@class,'specification-sec')]//li//text()"
        )

        detailed_description = self._clean(" ".join(details_text + spec_text))

        # ---------- SIZE (from outer listing) ---------- #
        size_text = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'product-listing-content')]//p[1]/text()")
        ))

        size_ft, size_ac = self.extract_size(size_text)

        # ---------- PRICE (from outer listing) ---------- #
        price_text = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'product-listing-content')]//h5/text()")
        ))

        price = self.extract_numeric_price(price_text, sale_type)

        # ---------- IMAGES ---------- #
        property_images = [
            urljoin(self.DOMAIN, img)
            for img in tree.xpath(
                "//div[contains(@class,'property-gallery-wrap')]//a/@href"
            )
        ]

        # ---------- BROCHURES ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath(
                "//h3[normalize-space()='Downloads']"
                "/following-sibling::ul[contains(@class,'download-sec-ul')]"
                "//a/@href"
            )
        ]

        # ---------- AGENT ---------- #
        agent_name = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'next-steps-info')]//h5/text()")
        ))

        agent_email = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'next-steps-info')]//a[contains(@href,'mailto:')]/@href")
        )).replace("mailto:", "")

        agent_phone = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'next-steps-info')]//a[contains(@href,'tel:')]/text()")
        ))

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(address_2),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Ingleby Trice",
            "agentName": agent_name,
            "agentCity": "",
            "agentEmail": agent_email,
            "agentPhone": agent_phone,
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": "",
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

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\.?\s*ft\.?|sqft|sf)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

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
            "per month", "pw", "per week", "rent", "per sq"
        ]):
            return ""

        m = re.search(r'[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)', t)
        if not m:
            return ""

        return m.group(1).replace(",", "")

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
        if "let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
