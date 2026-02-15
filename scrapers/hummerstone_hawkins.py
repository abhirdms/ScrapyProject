import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from lxml import html


class HummerstoneHawkinsScraperAbhi:
    BASE_URL = "https://hummerstonehawkins.com/search-results/?location=&commercial_property_type=&availability=&department=commercial"
    PAGE_URL = "https://hummerstonehawkins.com/search-results/page/{}/?location=&commercial_property_type=&availability=&department=commercial"
    DOMAIN = "https://hummerstonehawkins.com/"

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
        self.wait = WebDriverWait(self.driver, 15)

    # ---------------- RUN ---------------- #

    def run(self):
        page = 1

        while True:
            if page == 1:
                url = self.BASE_URL
            else:
                url = self.PAGE_URL.format(page)

            self.driver.get(url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//ul[contains(@class,'properties')]/li"
                )))
            except TimeoutException:
                break  # No more listings -> stop pagination

            tree = html.fromstring(self.driver.page_source)

            listing_urls = tree.xpath(
                "//div[@class='propertySummaryWrapper']/h3/a/@href"
            )

            if not listing_urls:
                break  # Safety stop

            for rel_url in listing_urls:
                try:
                    full_url = urljoin(self.DOMAIN, rel_url)
                    self.results.append(self.parse_listing(full_url))
                except Exception:
                    continue

            page += 1

        self.driver.quit()
        return self.results

    # ---------------- LISTING ---------------- #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h1[contains(@class,'property_title')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        display_address = self._clean(" ".join(
            tree.xpath("//h1[contains(@class,'property_title')]/text()")
        ))

        detailed_description_list = tree.xpath(
            "//div[@class='features']/ul/li/text()"
        )

        detailed_description = self._clean(" ".join(detailed_description_list))

        size_ft, size_ac = self.extract_size(detailed_description)

        sale_type = self.get_sale_type(tree)

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,

            "price": self.extract_price(tree),

            "propertySubType": self._clean(" ".join(
                tree.xpath("//li[@class='property-type']/text()")
            )),

            "propertyImage": [
                urljoin(self.DOMAIN, img)
                for img in tree.xpath(
                    "//a[contains(@class,'propertyhive-main-image')]/img/@src"
                )
            ],

            "detailedDescription": detailed_description,

            "sizeFt": size_ft,
            "sizeAc": size_ac,

            "postalCode": self.extract_postcode(display_address),

            "brochureUrl": tree.xpath(
                "//li[@class='action-brochure']/a/@href"
            ),

            "agentCompanyName": "Hummerstone & Hawkins",

            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",

            "tenure": self.get_tenure_from_description(detailed_description),

            "saleType": sale_type,
        }

        return obj

    # ---------------- HELPERS ---------------- #

    def extract_price(self, tree):
        rent = tree.xpath("//span[@class='commercial-rent']/text()")
        sale = tree.xpath("//span[@class='commercial-price']/text()")

        text = rent[0] if rent else sale[0] if sale else ""

        if not text:
            return ""

        text = text.replace("£", "").replace(",", "")
        numbers = re.findall(r"\d+(?:\.\d+)?", text)

        return numbers[0] if numbers else ""

    def get_sale_type(self, tree):
        raw = " ".join(
            tree.xpath("//li[@class='availability']/text()")
        ).lower()

        if "sale" in raw:
            return "For Sale"

        if "let" in raw:
            return "To Let"

        if "offer" in raw:
            return "Under Offer"

        return ""

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")

        size_ft = ""
        size_ac = ""

        sqft_match = re.search(r"(\d+(?:\.\d+)?)\s*(sq\s*ft|sqft)", text)
        if sqft_match:
            size_ft = int(float(sqft_match.group(1)))

        acre_match = re.search(r"(\d+(?:\.\d+)?)\s*(acre|acres)", text)
        if acre_match:
            size_ac = float(acre_match.group(1))

        return size_ft, size_ac

    def extract_postcode(self, text):
        if not text:
            return ""

        text = text.upper()
        match = re.search(r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b", text)
        return match.group().strip() if match else ""

    def get_tenure_from_description(self, text):
        if not text:
            return ""

        t = text.lower()

        if "freehold" in t:
            return "Freehold"

        if "leasehold" in t or "lease" in t:
            return "Leasehold"

        return ""

    def _clean(self, val):
        return val.strip() if val else ""
