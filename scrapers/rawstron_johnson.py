import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class RawstronJohnsonScraper:
    BASE_URL = "https://rj-ltd.co.uk/available-properties/"
    DOMAIN = "https://rj-ltd.co.uk"

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

        try:
            self.wait.until(EC.presence_of_element_located((
                By.XPATH,
                "//div[contains(@class,'jet-listing-grid__item')]"
            )))
        except Exception:
            self.driver.quit()
            return self.results

        tree = html.fromstring(self.driver.page_source)

        items = tree.xpath(
            "//div[contains(@class,'jet-listing-grid__item') and @data-post-id]"
        )

        for item in items:

            display_address = self._clean(" ".join(
                item.xpath(".//h3[contains(@class,'elementor-heading-title')]/text()")
            ))

            brochure_urls = self._extract_brochure_urls(item)

            if not brochure_urls:
                continue

            listing_url = brochure_urls[0]

            if listing_url in self.seen_urls:
                continue

            self.seen_urls.add(listing_url)

            obj = self.parse_listing(
                listing_url,
                display_address,
                brochure_urls
            )

            if obj:
                self.results.append(obj)

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url, display_address, brochure_urls):

        sale_type = ""

        detailed_description = ""
        property_sub_type = ""

        size_ft = ""
        size_ac = ""

        tenure = ""
        price = ""

        property_images = []

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Rawstron Johnson",
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

    def _extract_brochure_urls(self, item):
        hrefs = item.xpath(
            ".//a[not(starts-with(@href,'mailto:'))]/@href"
        )

        brochure_urls = []
        for href in hrefs:
            if ".pdf" not in href.lower():
                continue

            full_url = urljoin(self.DOMAIN, href)
            if full_url not in brochure_urls:
                brochure_urls.append(full_url)

        return brochure_urls

    def extract_postcode(self, text):
        if not text:
            return ""

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        t = text.upper()
        m = re.search(FULL, t) or re.search(PARTIAL, t)
        return m.group() if m else ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
