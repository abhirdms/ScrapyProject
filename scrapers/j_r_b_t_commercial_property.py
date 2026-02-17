import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class JRBTCommercialPropertyScraper:
    BASE_URL = "https://www.jrbtcommercialproperty.co.uk/current-properties/"
    DOMAIN = "https://www.jrbtcommercialproperty.co.uk"

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
            "//div[contains(@class,'cp__item')]"
        )))

        tree = html.fromstring(self.driver.page_source)
        listing_nodes = tree.xpath("//div[contains(@class,'cp__item')]")

        for node in listing_nodes:
            pdf_url = node.xpath(".//a[contains(@href,'.pdf')]/@href")
            if not pdf_url:
                continue

            url = urljoin(self.DOMAIN, pdf_url[0])

            if url in self.seen_urls:
                continue
            self.seen_urls.add(url)

            try:
                obj = self.parse_listing(node, url)
                if obj:
                    self.results.append(obj)
            except Exception:
                continue

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, node, url):

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            node.xpath(".//div[contains(@class,'cp__address')]//text()")
        ))

        # ---------- SALE TYPE (ROBUST MULTI-SOURCE LOGIC) ---------- #
        sale_type_sources = []

        sale_type_sources.append(
            self._clean(" ".join(
                node.xpath(".//div[contains(@class,'cp__sale-status')]/div/text()")
            ))
        )

        sale_type_sources.append(
            self._clean(" ".join(
                node.xpath(".//div[contains(@class,'cp__banner')]/div/text()")
            ))
        )

        sale_type_sources.append(
            self._clean(" ".join(
                node.xpath(".//div[contains(@class,'cp__address--title')]/text()")
            ))
        )

        sale_type_sources.append(display_address)

        combined_sale_text = " ".join(
            [s for s in sale_type_sources if s]
        )

        sale_type = self.normalize_sale_type(combined_sale_text)

        # ---------- PRICE (STORE ONLY IF FOR SALE) ---------- #
        raw_price = self._clean(" ".join(
            node.xpath(
                ".//div[contains(@class,'cp__price') and not(contains(@class,'wrap'))]/text()"
            )
        ))

        price = ""
        if (
            sale_type == "For Sale"
            and raw_price
            and "POA" not in raw_price.upper()
        ):
            numeric = re.sub(r"[^\d]", "", raw_price)
            price = numeric if numeric else ""

        # ---------- IMAGE (FROM STYLE ATTRIBUTE) ---------- #
        style_attr = node.xpath(".//div[contains(@class,'cp__image')]/@style")
        property_images = []

        if style_attr:
            match = re.search(r"url\(['\"]?(.*?)['\"]?\)", style_attr[0])
            if match:
                property_images.append(match.group(1))

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in node.xpath(".//a[contains(@href,'.pdf')]/@href")
        ]

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": property_images,
            "detailedDescription": "",
            "sizeFt": "",
            "sizeAc": "",
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "JRBT Commercial Property",
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

    # ===================== HELPERS ===================== #

    def extract_postcode(self, text):
        if not text:
            return ""

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        t = text.upper()
        m = re.search(FULL, t) or re.search(PARTIAL, t)
        return m.group() if m else ""

    def normalize_sale_type(self, text):
        if not text:
            return ""

        t = text.lower()

        # Highest priority: To Let
        if "to let" in t or re.search(r"\blet\b", t):
            return "To Let"

        # Explicit For Sale
        if "for sale" in t:
            return "For Sale"

        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
