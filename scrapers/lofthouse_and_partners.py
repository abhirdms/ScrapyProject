import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class LofthouseAndPartnersScraper:
    BASE_URL = "https://lofthouseandpartners.co.uk/property-search/#results"
    DOMAIN = "https://lofthouseandpartners.co.uk"

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

        # Wait for listings to load
        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            '//article[contains(@class,"type-property")]'
        )))

        # Handle "Load More" button
        while True:
            try:
                load_more = self.driver.find_element(By.ID, "wpas-load-btn")
                if load_more.is_displayed():
                    self.driver.execute_script("arguments[0].click();", load_more)
                    self.wait.until(EC.presence_of_all_elements_located((
                        By.XPATH,
                        '//article[contains(@class,"type-property")]'
                    )))
                else:
                    break
            except Exception:
                break

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            '//article[contains(@class,"type-property")]'
            '//h3[contains(@class,"entry-title")]/a/@href'
        )

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
            '//h1[@class="entry-title"]'
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath('//h1[@class="entry-title"]/text()')
        ))

        # ---------- PRICE ---------- #
        price_raw = self._clean(" ".join(
            tree.xpath(
                '//dt[normalize-space()="Price"]/following-sibling::dd[1]/text()'
            )
        ))

        sale_type = self.normalize_sale_type(price_raw)
        price = self.extract_numeric_price(price_raw, sale_type)

        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type = ", ".join(
            tree.xpath(
                '//dt[normalize-space()="Categories"]'
                '/following-sibling::dd[1]//span/text()'
            )
        )

        # ---------- DESCRIPTION ---------- #
        detailed_description = self._clean(" ".join(
            tree.xpath(
                '//div[contains(@class,"entry-content")]//ul/li/text()'
            )
        ))

        # ---------- IMAGE ---------- #
        property_images = [
            urljoin(self.DOMAIN, src)
            for src in tree.xpath(
                '//aside[contains(@class,"sidebar")]//img/@src'
            )
        ]

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href.strip())
            for href in tree.xpath(
                '//aside[contains(@class,"sidebar")]'
                '//a[contains(@href,".pdf")]/@href'
            )
        ]

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": "",
            "sizeAc": "",
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Lofthouse and Partners",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": "",
            "saleType": sale_type,
        }

        return obj

    # ===================== HELPERS ===================== #

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

        m = re.search(r'£\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?', t)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))
        if "m" in m.group(0):
            num *= 1_000_000

        return str(int(num))

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
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
