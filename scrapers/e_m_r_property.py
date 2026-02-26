import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class EMRPropertyScraper:
    BASE_URL = "https://emrproperty.co.uk/instructions"
    DOMAIN = "https://emrproperty.co.uk"

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

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//a[@data-aid='PDF_DOWNLOAD_LINK_RENDERED']"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_blocks = tree.xpath(
            "//div[@data-ux='Widget'][.//a[@data-aid='PDF_DOWNLOAD_LINK_RENDERED']]"
        )

        for block in listing_blocks:

            display_address = self._clean(" ".join(
                block.xpath(".//p[@data-aid='PDF_HEADING_RENDERED']/text()")
            ))

            pdf_url = block.xpath(
                ".//a[@data-aid='PDF_DOWNLOAD_LINK_RENDERED']/@href"
            )

            if not pdf_url:
                continue

            pdf_url = pdf_url[0]

            # Fix protocol-relative URLs
            if pdf_url.startswith("//"):
                pdf_url = "https:" + pdf_url

            if pdf_url in self.seen_urls:
                continue

            self.seen_urls.add(pdf_url)

            obj = self.parse_listing(display_address, pdf_url)
            if obj:
                self.results.append(obj)

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, display_address, pdf_url):

        # ---------- IMAGE (Derived from PDF) ---------- #
        property_images = []
        if pdf_url:
            preview_img = pdf_url + "?width=800"
            property_images.append(preview_img)

        detailed_description = ""
        size_ft = ""
        size_ac = ""
        tenure = ""
        price = ""
        property_sub_type = ""
        sale_type = ""

        obj = {
            "listingUrl": pdf_url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": [pdf_url],
            "agentCompanyName": "EMR Property",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }

        print("*****" * 10)
        print(obj)
        print("*****" * 10)

        return obj

    # ===================== HELPERS ===================== #

    def extract_postcode(self, text: str):
        if not text:
            return ""

        text = text.upper()

        full_pattern = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        partial_pattern = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        match = re.search(full_pattern, text)
        if match:
            return match.group().strip()

        match = re.search(partial_pattern, text)
        return match.group().strip() if match else ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""