import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class HebCharteredSurveyorsScraper:
    BASE_URLS = {
        "To Let": "https://www.rightmove.co.uk/commercial-property-to-let/find/HEB-Property-Consultants/Nottingham.html?locationIdentifier=BRANCH%5E168662",
        "For Sale": "https://www.rightmove.co.uk/commercial-property-for-sale/find/HEB-Property-Consultants/Nottingham.html?locationIdentifier=BRANCH%5E168662",
    }

    DOMAIN = "https://www.rightmove.co.uk"

    def __init__(self):
        self.results = []
        self.seen_urls = set()

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")

        service = Service("/usr/bin/chromedriver")
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 20)

    # ============================================================
    # RUN
    # ============================================================

    def run(self):

        for sale_type, base_url in self.BASE_URLS.items():

            self.driver.get(base_url)

            self.wait.until(EC.presence_of_element_located((
                By.XPATH,
                "//div[contains(@class,'PropertyCard_propertyCardContainerWrapper')]"
            )))

            tree = html.fromstring(self.driver.page_source)

            # ---- Pagination ----
            page_indexes = tree.xpath(
                "//select[@data-testid='paginationSelect']/option/@value"
            )
            page_indexes = [int(v) for v in page_indexes] if page_indexes else [0]

            for index in page_indexes:

                page_url = f"{base_url}&index={index}"
                self.driver.get(page_url)

                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'PropertyCard_propertyCardContainerWrapper')]"
                )))

                tree = html.fromstring(self.driver.page_source)

                listing_urls = tree.xpath(
                    "//a[@data-testid='property-details-lozenge']/@href"
                )

                for relative in listing_urls:

                    url = urljoin(self.DOMAIN, relative.split("#")[0])

                    if url in self.seen_urls:
                        continue
                    self.seen_urls.add(url)

                    try:
                        obj = self.parse_listing(url, sale_type)
                        if obj:
                            self.results.append(obj)
                    except Exception:
                        continue

        self.driver.quit()
        return self.results

    # ============================================================
    # LISTING PAGE
    # ============================================================

    def parse_listing(self, url, sale_type):

        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h1[@itemprop='streetAddress']"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- ADDRESS ----------
        display_address = self._clean(" ".join(
            tree.xpath("//h1[@itemprop='streetAddress']/text()")
        ))

        # ---------- PRICE ----------
        price_raw = self._clean(" ".join(
            tree.xpath("//div[@data-testid='primaryPrice']//span/text()")
        ))

        price = self.normalize_price(price_raw, sale_type)

        # ---------- PROPERTY TYPE ----------
        property_sub_type = self._clean(" ".join(
            tree.xpath(
                "//span[@data-testid='info-reel-SECTOR-text']//p/text()"
            )
        ))

        # ---------- DESCRIPTION ----------
        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//h2[normalize-space()='Description']"
                "/following-sibling::div[1]//text()"
            )
        ))

        # ---------- SIZE ----------
        size_ft, size_ac = self.extract_size_from_info_reel(tree)


        # ---------- IMAGES (SCHEMA SAFE) ----------
        property_images = list(set(
            tree.xpath("//meta[@itemprop='contentUrl']/@content")
        ))


        tenure = self.extract_tenure(detailed_description)

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
            "brochureUrl": [],
            "agentCompanyName": "heb Chartered Surveyors",
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


    def extract_size_from_info_reel(self, tree):

        size_ft = ""
        size_ac = ""

        size_texts = tree.xpath(
            "//dl[@id='info-reel']"
            "//span[@data-testid='info-reel-SIZE-text']/p/text()"
        )

        if not size_texts:
            return size_ft, size_ac

        for text in size_texts:

            cleaned = text.lower().replace(",", "").strip()

            # ---- SQ FT ----
            if "sq ft" in cleaned:
                m = re.search(r'(\d+(?:\.\d+)?)', cleaned)
                if m:
                    size_ft = float(m.group(1))

            # ---- ACRES ----
            if "acre" in cleaned:
                m = re.search(r'(\d+(?:\.\d+)?)', cleaned)
                if m:
                    size_ac = float(m.group(1))

        return size_ft, size_ac


    def normalize_price(self, price_text, sale_type):

        if sale_type != "For Sale":
            return ""

        if not price_text:
            return ""

        if "poa" in price_text.lower():
            return ""

        m = re.search(r'£\s?([\d,]+)', price_text)
        if not m:
            return ""

        return m.group(1).replace(",", "")

    def extract_tenure(self, text):
        if not text:
            return ""
        t = text.lower()
        if "freehold" in t:
            return "Freehold"
        if "leasehold" in t:
            return "Leasehold"
        return ""

    def extract_postcode(self, text):
        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        t = text.upper()
        m = re.search(FULL, t) or re.search(PARTIAL, t)
        return m.group() if m else ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
