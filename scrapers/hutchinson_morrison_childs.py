from urllib.parse import urljoin
import re

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class HutchinsonMorrisonChildsScraperAbhi:
    BASE_URL = "https://www.hmc.london/available-property"
    DOMAIN = "https://www.hmc.london"

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
        self.driver.get(self.BASE_URL)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'col-md-4')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        property_blocks = tree.xpath("//div[contains(@class,'col-md-4')]")

        for block in property_blocks:
            try:
                self.results.append(self.parse_listing(block))
            except Exception:
                continue

        self.driver.quit()
        return self.results

    # ---------------- PARSE ---------------- #

    def parse_listing(self, block):

        listing_url = block.xpath(".//a/@href")
        listing_url = urljoin(self.DOMAIN, listing_url[0]) if listing_url else ""

        display_address = block.xpath(".//p/b/text()")
        display_address = display_address[0].strip() if display_address else ""

        # Extract size (sq ft)
        size_text = block.xpath(".//p/text()[contains(.,'sq ft')]")
        size_text = size_text[0].strip() if size_text else ""

        size_ft = self.extract_size(size_text)

        brochure = block.xpath(".//a[contains(@href,'.pdf')]/@href")
        brochure_url = urljoin(self.DOMAIN, brochure[0]) if brochure else ""

        image = block.xpath(".//a[contains(@href,'.pdf')]/img/@src")
        property_image = [urljoin(self.DOMAIN, image[0])] if image else []

        sale_type = block.xpath(".//p[@class='orange']/text()")
        sale_type = sale_type[0].strip() if sale_type else ""

        obj = {
            "listingUrl": listing_url,
            "displayAddress": display_address,

            "price": "",  # Not available

            "propertySubType": "",

            "propertyImage": property_image,

            "detailedDescription": size_text,

            "sizeFt": size_ft,
            "sizeAc": "",

            "postalCode": self.extract_postcode(display_address),

            "brochureUrl": brochure_url,

            "agentCompanyName": "Hutchinson Morrison Childs",

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

    # ---------------- HELPERS ---------------- #

    def extract_size(self, text):
        if not text:
            return ""

        text = text.replace(",", "")
        match = re.search(r"(\d+(?:\.\d+)?)", text)

        return int(float(match.group(1))) if match else ""

    def extract_postcode(self, text):
        if not text:
            return ""

        text = text.upper()
        match = re.search(r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b", text)

        return match.group().strip() if match else ""
