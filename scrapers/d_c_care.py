import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class DCCareScraper:
    BASE_URL = "https://www.dccare.co.uk/buying-with-us/search-results/"
    DOMAIN = "https://www.dccare.co.uk"

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
        page = 1

        while True:
            page_url = self.BASE_URL if page == 1 else f"{self.BASE_URL}page/{page}/"
            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'ed-search-results-single-property')]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            listings = tree.xpath(
                "//div[contains(@class,'ed-search-results-single-property')]"
            )

            if not listings:
                break

            for card in listings:
                try:
                    obj = self.parse_listing(card)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

            page += 1

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, card):

        # ---------- TITLE ---------- #
        title = self._clean(" ".join(
            card.xpath(
                ".//span[contains(@class,'ed-search-results-single-property__title')]/text()"
            )
        ))

        # ---------- REF NUMBER ---------- #
        ref_text = self._clean(" ".join(
            card.xpath(
                ".//li[contains(@class,'ed-search-results-single-property__ref')]/text()"
            )
        ))

        ref_match = re.search(r"Ref:\s*(\d+)", ref_text)
        ref_no = ref_match.group(1) if ref_match else ""

        listing_url = f"{self.BASE_URL}?ref={ref_no}" if ref_no else title

        if listing_url in self.seen_urls:
            return None
        self.seen_urls.add(listing_url)

        # ---------- PRICE ---------- #
        price_text = self._clean(" ".join(
            card.xpath(
                ".//span[contains(@class,'ed-search-results-single-property__price')]/text()"
            )
        ))

        price = self.extract_numeric_price(price_text, "For Sale")

        # ---------- PROPERTY TYPE ---------- #
        property_sub_type = self._clean(" ".join(
            card.xpath(
                ".//li[contains(@class,'ed-search-results-single-property__type')]/text()"
            )
        )).replace("Type:", "").strip()

        # ---------- BEDS ---------- #
        beds_text = self._clean(" ".join(
            card.xpath(
                ".//li[contains(@class,'ed-search-results-single-property__beds')]/text()"
            )
        ))

        beds = re.search(r"Beds:\s*(\d+)", beds_text)
        beds_value = beds.group(1) if beds else ""

        # ---------- IMAGE ---------- #
        property_images = card.xpath(
            ".//img[contains(@class,'ed-search-results-single-property__image')]/@src"
        )

        # ---------- DESCRIPTION (COMBINED) ---------- #
        detailed_description = " ".join(
            part for part in [
                title,
                property_sub_type,
                f"Beds: {beds_value}" if beds_value else "",
                f"Reference: {ref_no}" if ref_no else ""
            ] if part
        )

        obj = {
            "listingUrl": "",
            "displayAddress": title,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": "",
            "sizeAc": "",
            "postalCode": "",
            "brochureUrl": [],
            "agentCompanyName": "DC Care",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": "",
            "saleType": "",
        }

        print("*****" * 10)
        print(obj)
        print("*****" * 10)

        return obj

    # ===================== HELPERS ===================== #

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale":
            return ""

        if not text:
            return ""

        t = text.lower()

        if "poa" in t or "price on application" in t:
            return ""

        m = re.search(r'[£]\s*(\d+(?:,\d{3})*(?:\.\d+)?)', text)
        if not m:
            return ""

        return m.group(1).replace(",", "")

    def _clean(self, val):
        return " ".join(val.split()) if val else ""