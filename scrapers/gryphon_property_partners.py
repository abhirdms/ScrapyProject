import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class GryphonPropertyPartnersScraper:
    BASE_URL = "https://www.gryphonpropertypartners.com/Properties.html"
    DOMAIN = "https://www.gryphonpropertypartners.com/"

    def __init__(self):
        self.results = []

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"

        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-software-rasterizer")
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.add_argument("--window-size=1920,1080")

        service = Service("/usr/bin/chromedriver")

        self.driver = webdriver.Chrome(
            service=service,
            options=chrome_options
        )

        self.wait = WebDriverWait(self.driver, 20)

    # ---------------- RUN ---------------- #

    def run(self):
        self.driver.get(self.BASE_URL)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[@id='properties']//div[contains(concat(' ', normalize-space(@class), ' '), ' prop-box ')]"
        )))
        tree = html.fromstring(self.driver.page_source)
        listing_urls = tree.xpath(
            "//div[@id='properties']"
            "//div[contains(concat(' ', normalize-space(@class), ' '), ' prop-box ')]"
            "/a/@href"
        )
        for rel_url in listing_urls:
            try:
                url = urljoin(self.DOMAIN, rel_url)
                self.results.append(self.parse_listing(url))
            except Exception:
                continue

        self.driver.quit()
        return self.results

    # ---------------- LISTING ---------------- #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'prop-title')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        display_address = self._clean(" ".join(
                tree.xpath("//div[@class='sing-prop-title-left']/*[2]//text()")
            ))
        
        detailedDescription=self._clean(" ".join(
                tree.xpath("//div[contains(@class,'sing-prop-info-text')]//text()")
            ))

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": "",
            "propertySubType": "",
            "propertyImage": [
                urljoin(self.DOMAIN, img)
                for img in tree.xpath(
                    "//div[@id='MainContent_pnlGallery']"
                    "//a[contains(@class,'sing-prop-img')]/@href"
                )
            ],
            "detailedDescription":detailedDescription,
            "sizeFt": "",
            "sizeAc": "",

            "postalCode": self.extract_postcode(display_address),

            "brochureUrl": [
                self.normalize_url(u) for u in tree.xpath(
                    "//div[contains(@class,'extra-box-top')]"
                    "//div[contains(@class,'dl-list')]//a/@href"
                ) if self.normalize_url(u)
            ],

            "agentCompanyName": "Gryphon Property Partners",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": self.get_tenure(detailedDescription),
            "saleType": self.get_sale_type(detailedDescription),
        }
        return obj


    def get_tenure(self, text):
        if not text:
            return ""

        t = text.lower()

        if "freehold" in t:
            return "Freehold"

        if "leasehold" in t or "lease" in t:
            return "Leasehold"

        return ""
    
    def get_sale_type(self, text):
        if not text:
            return ""
        text= text.lower()

        if "for sale" in text:
            return "For Sale"
        if "to let" in text:
            return "To Let"
        return ""

    def extract_postcode(self, text):
        if not text:
            return ""

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        text = text.upper()
        m = re.search(FULL, text) or re.search(PARTIAL, text)
        return m.group().strip() if m else ""

    def normalize_url(self, url):
        return urljoin(self.DOMAIN, url) if url else ""


    def _clean(self, val):
        return val.strip() if val else ""
