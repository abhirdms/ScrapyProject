import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class Pk3AgencyScraperaashishgiri:
    BASE_URL = "https://pk3.agency/investments/"
    DOMAIN = "https://pk3.agency/"

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

    # ---------------- RUN ---------------- #

    def run(self):
        self.driver.get(self.BASE_URL)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//article[@class='property-card']//a[@class='property-card-link']"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            "//article[@class='property-card']//a[@class='property-card-link']/@href"
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
            "//section[contains(@class,'hero')]//h1"
        )))

        tree = html.fromstring(self.driver.page_source)

        display_address = self._clean(" ".join(
            tree.xpath("//div[@class='hero-content']//p[@class='hero-subtitle']/text()")
        ))

        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//div[@class='property-description']"
                "//div[contains(@class,'property-content')]//*[self::p or self::li]//text()"
            )
        ))

        price_text = self._clean(" ".join(
            tree.xpath(
                "//div[@class='property-image-block']"
                "//span[@class='property-metric-label' and text()='Price']"
                "/following-sibling::span[@class='property-metric-value']/text()"
            )
        ))

        postcode_text = " ".join(
            tree.xpath("//div[@class='hero-content']//h1/text()")
        )

        obj = {
            "listingUrl": url,

            "displayAddress": display_address,

            "price": self.extract_numeric_price(price_text, ""),

            "propertySubType": self._clean(" ".join(
                tree.xpath(
                    "//div[@class='property-metrics']"
                    "//span[contains(normalize-space(),'Rent')]/text()"
                )
            )),

            "propertyImage": [
                img
                for img in tree.xpath(
                    "//div[@class='property-image-block']"
                    "//img[@class='property-thumbnail-image']/@src"
                )
            ],

            "detailedDescription": detailed_description,

            "sizeFt": "",
            "sizeAc": "",

            "postalCode": self.extract_postcode(postcode_text),

            "brochureUrl": [
                urljoin(self.DOMAIN, u)
                for u in tree.xpath(
                    "//div[@class='property-card-box']//a[@target='_blank']/@href"
                )
            ],

            "agentCompanyName": "PK3 Agency",

            "agentName": self._clean(" ".join(
                tree.xpath(
                    "//p[contains(@class,'property-card-box-text')]//a/text()"
                )
            )),

            "agentCity": "",
            "agentEmail": self._clean(" ".join(
                tree.xpath(
                    "//p[contains(@class,'property-card-box-text')]//a[starts-with(@href,'mailto:')]/text()"
                )
            )),
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",

            "tenure": self._clean(" ".join(
                tree.xpath(
                    "//div[@class='property-metrics']"
                    "//span[contains(normalize-space(),'Rent')]/text()"
                )
            )),

            "saleType": "",
        }

        return obj

    # ---------------- HELPERS ---------------- #

    def extract_postcode(self, text):
        if not text:
            return ""

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        text = text.upper()
        m = re.search(FULL, text) or re.search(PARTIAL, text)
        return m.group().strip() if m else ""

    def extract_numeric_price(self, text, sale_type):
        if not text:
            return ""

        raw = text.lower()

        if any(k in raw for k in [
            "poa",
            "price on application",
            "on application",
            "subject to contract"
        ]):
            return ""

        raw = raw.replace("£", "").replace(",", "")
        raw = re.sub(r"(to|–|—)", "-", raw)

        numbers = re.findall(r"\d+(?:\.\d+)?", raw)
        if not numbers:
            return ""

        price = min(float(n) for n in numbers)
        return str(int(price)) if price.is_integer() else str(price)

    def _clean(self, val):
        return val.strip() if val else ""
