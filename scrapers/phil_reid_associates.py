import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class PhilReidScraperaashishgiri:
    BASE_URL = "https://www.philreidassociates.com/index.php/property-listings/"
    DOMAIN = "https://www.philreidassociates.com/"

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
            "//a[contains(@class,'av-masonry-entry')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            "//a[contains(@class,'av-masonry-entry')]/@href"
        )

        for url in listing_urls:
            try:
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
            "//section[contains(@class,'av_textblock_section')]//h3"
        )))

        tree = html.fromstring(self.driver.page_source)

        display_address = self._clean(" ".join(
            tree.xpath(
                "//section[contains(@class,'av_textblock_section')]//h3/strong[2]/text()"
            )
        ))

        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//div[@class='avia_textblock' and @itemprop='text']//text()"
            )
        ))

        size_ft, size_ac = self.extract_size(
            text=self._clean(" ".join(
                tree.xpath("//span[@id='lblSizes']/text()")
            ))
        )

        sale_type = self.get_sale_type(tree)

        obj = {
            "listingUrl": url,

            "displayAddress": display_address,

            "price": self.extract_numeric_price(
                " ".join(
                    tree.xpath("//h3[contains(.,'£')]/text()[contains(.,'£')]")
                ),
                sale_type
            ),

            "propertySubType": self._clean(" ".join(
                tree.xpath("//span[@id='lblPropertyType']/text()")
            )),

            "propertyImage": [
                urljoin(self.DOMAIN, img)
                for img in tree.xpath(
                    "//div[contains(@class,'avia-image-container')]//img[contains(@class,'avia_image')]/@src"
                    " | "
                    "//div[contains(@class,'avia-gallery')]//a[@data-rel]/@href"
                )
            ],

            "detailedDescription": detailed_description,

            "sizeFt": size_ft,
            "sizeAc": size_ac,

            "postalCode": self.extract_postcode(display_address),

            "brochureUrl": [
                urljoin(self.DOMAIN, u)
                for u in tree.xpath("//a[contains(@class,'av-download-btn')]/@href")
            ],

            "agentCompanyName": "Phil Reid Associates",
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

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower()
        text = text.replace(",", "")

        size_ft = ""
        size_ac = ""

        sqft = re.search(r'(\d+(?:\.\d+)?)\s*(sq\s*ft|sqft)', text)
        if sqft:
            size_ft = int(float(sqft.group(1)))

        acres = re.search(r'(\d+(?:\.\d+)?)\s*(acres?|acre|ac)', text)
        if acres:
            size_ac = round(float(acres.group(1)), 3)

        return size_ft, size_ac

    def get_sale_type(self, tree):
        raw = " ".join(
            tree.xpath("//span[@class='is-uppercase']/text()")
        ).lower()

        if "for sale" in raw:
            return "For Sale"
        if "to let" in raw:
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

    def extract_numeric_price(self, text, sale_type):
        if not text:
            return ""

        if not sale_type or sale_type.lower() != "for sale":
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

    def get_tenure_from_description(self, text):
        if not text:
            return ""

        t = text.lower()

        if "freehold" in t:
            return "Freehold"
        if "lease" in t:
            return "Leasehold"

        return ""

    def _clean(self, val):
        return val.strip() if val else ""
