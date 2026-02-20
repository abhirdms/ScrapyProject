import re
import time
import requests
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class AdvantageInvestmentScraper:
    BASE_URL = "https://advantageinvestment.co.uk/investment-properties/"
    DOMAIN = "https://advantageinvestment.co.uk"

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

    # ============================= RUN ============================= #

    def run(self):
        session = requests.Session()
        page = 1
        seen = set()

        while True:
            payload = {
                "action": "jet_engine_ajax",
                "handler": "listing_load_more",
                "query[post_status][]": "publish",
                "query[post_type]": "properties",
                "query[posts_per_page]": "9",
                "query[paged]": str(page - 1),
                "query[ignore_sticky_posts]": "1",
                "query[suppress_filters]": "false",
                "widget_settings[lisitng_id]": "21267",
                "widget_settings[posts_num]": "9",
                "widget_settings[columns]": "3",
                "widget_settings[use_load_more]": "yes",
                "widget_settings[load_more_type]": "scroll",
                "page_settings[page]": str(page),
            }

            response = session.post(
                f"{self.BASE_URL}?nocache={int(time.time())}",
                data=payload,
                headers={
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": self.BASE_URL,
                    "Origin": self.DOMAIN,
                }
            )

            if response.status_code != 200:
                break

            try:
                json_data = response.json()
                html_block = json_data.get("data", {}).get("html", "")
            except Exception:
                break

            if not html_block:
                break

            tree = html.fromstring(html_block)

            listing_urls = tree.xpath(
                "//div[contains(@class,'jet-listing-grid__item')]"
                "//a[contains(@class,'jet-listing-dynamic-link__link')]/@href"
            )

            if not listing_urls:
                break

            new_urls = []
            for url in listing_urls:
                full_url = urljoin(self.DOMAIN, url)
                if full_url not in seen:
                    seen.add(full_url)
                    new_urls.append(full_url)

            if not new_urls:
                break

            for full_url in new_urls:
                self.results.append(self.parse_listing(full_url))

            page += 1

        self.driver.quit()
        return self.results

    # ============================= LISTING ============================= #

    def parse_listing(self, url):
        self.driver.get(url)

        # Stable wait condition
        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h1[contains(@class,'jet-breadcrumbs__title')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # -------- ADDRESS -------- #
        display_address = self._clean(" ".join(
            tree.xpath(
                "(//h1[contains(@class,'jet-breadcrumbs__title')]"
                "/ancestor::section[1]"
                "//div[contains(@class,'jet-listing-dynamic-field__content')])[1]/text()"
            )
        ))

        postal_code = self.extract_postcode(display_address)

        # -------- PRICE -------- #
        price_text = " ".join(
            tree.xpath(
                "//div[contains(@class,'jet-listing-dynamic-field__content') "
                "and contains(.,'£')]/text()"
            )
        )
        price = self.extract_price(price_text)

        # -------- IMAGES (FULL SIZE) -------- #
        images = tree.xpath(
            "//div[contains(@class,'elementor-image-carousel')]//a/@href"
        )

        # -------- DESCRIPTION (FULL SECTION) -------- #
        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//h6[normalize-space()='Description']"
                "/ancestor::section[1]"
                "//div[contains(@class,'jet-listing-dynamic-field__content')]//text()"
            )
        ))

        sizeFt, sizeAc = self.extract_size(detailed_description)
        tenure = self.extract_tenure(detailed_description)

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": images,
            "detailedDescription": detailed_description,
            "sizeFt": sizeFt,
            "sizeAc": sizeAc,
            "postalCode": postal_code,
            "brochureUrl": [],
            "agentCompanyName": "Advantage Investment",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": "For Sale",
        }

        return obj

    # ============================= HELPERS ============================= #

    def extract_price(self, text):
        if not text:
            return ""

        text = text.lower()

        # Ignore rent contexts
        if any(x in text for x in ["per annum", "pa", "pcm", "pw", "rent", "psf"]):
            return ""

        text = text.replace(",", "")
        m = re.search(r"£\s?(\d+(?:\.\d+)?)", text)

        return m.group(1) if m else ""

    def extract_postcode(self, text):
        if not text:
            return ""

        text = text.upper()

        FULL = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b"
        PARTIAL = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\b"

        m = re.search(FULL, text)
        if m:
            return m.group(0)

        m = re.search(PARTIAL, text)
        if m:
            return m.group(0)

        return ""

    def extract_tenure(self, text):
        if not text:
            return ""

        text = text.lower()

        if "freehold" in text:
            return "Freehold"
        if "leasehold" in text:
            return "Leasehold"

        return ""

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower()
        text = text.replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        # SQ FT
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        # ACRES
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|ac\b)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        return size_ft, size_ac

    def _clean(self, text):
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()