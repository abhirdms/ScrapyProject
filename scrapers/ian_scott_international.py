import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from urllib.parse import urlparse, urlunparse

from lxml import html


class IanScottInternationalScraper:
    BASE_URLS = {
        "For Sale": [
            "https://ianscott.com/advanced-search/?status=for-sale",
            "https://ianscott.com/advanced-search/?status=lease-for-sale",
            "https://ianscott.com/advanced-search/?status=under-offer",
        ],
        "To Let": [
            "https://ianscott.com/advanced-search/?status=to-let",
            "https://ianscott.com/advanced-search/?status=let",
            "https://ianscott.com/advanced-search/?status=short-term",
        ]
    }


    DOMAIN = "https://ianscott.com"

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

    # ===================== RUN ===================== #

    def run(self):
        for sale_type, url_list in self.BASE_URLS.items():

            for base_url in url_list:
                page = 1

                while True:

                    if page == 1:
                        page_url = base_url
                    else:
                        parsed = urlparse(base_url)
                        page_url = (
                            f"{parsed.scheme}://{parsed.netloc}"
                            f"/advanced-search/page/{page}/"
                            f"?{parsed.query}"
                        )

                    self.driver.get(page_url)

                    # Small wait just for page load
                    self.driver.implicitly_wait(2)

                    tree = html.fromstring(self.driver.page_source)

                    listing_urls = tree.xpath(
                        "//div[contains(@class,'ere-item-wrap')]"
                        "//h2[contains(@class,'property-title')]/a/@href"
                    )

                    if not listing_urls:
                        break

                    tree = html.fromstring(self.driver.page_source)

                    listing_urls = tree.xpath(
                        "//div[contains(@class,'ere-item-wrap')]"
                        "//h2[contains(@class,'property-title')]/a/@href"
                    )

                    if not listing_urls:
                        break

                    for url in listing_urls:
                        if url in self.seen_urls:
                            continue

                        self.seen_urls.add(url)

                        try:
                            obj = self.parse_listing(url, sale_type)
                            if obj:
                                self.results.append(obj)
                        except Exception:
                            continue

                    page += 1

        self.driver.quit()
        return self.results


    # ===================== LISTING ===================== #

    def parse_listing(self, url, sale_type):

        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'property-heading')]//h2"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'property-heading')]//h2//text()"
            )
        ))

        # ---------- SALE TYPE VALIDATION ---------- #
        status_list = [
            self._clean(s)
            for s in tree.xpath(
                "//div[contains(@class,'property-status')]//span/text()"
            )
            if s.strip()
        ]

        if status_list:
            normalized = [s.lower() for s in status_list]

            if any("sale" in s for s in normalized):
                sale_type = "For Sale"
            elif any("let" in s for s in normalized):
                sale_type = "To Let"


        # ---------- PROPERTY TYPE ---------- #
        property_sub_type = ", ".join([
            self._clean(x)
            for x in tree.xpath(
                "//span[contains(@class,'ere__property-type')]//a/text()"
            )
        ])

        # ---------- DESCRIPTION ---------- #
        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'property-description')]"
                "//div[contains(@class,'ere-property-element')]"
                "//text()[normalize-space()]"
            )
        ))

        # ---------- SIZE (TOTAL PRIORITY) ---------- #
        total_row = " ".join(
            tree.xpath(
                "//table//tr[.//strong[contains(text(),'Total')]]//text()"
            )
        )

        size_ft, size_ac = self.extract_size(total_row)

        if not size_ft and not size_ac:
            size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- PRICE ---------- #
        price_text = self._clean(" ".join(
            tree.xpath(
                "//span[contains(@class,'property-price')]/text()"
            )
        ))

        price = self.extract_price(price_text or detailed_description, sale_type)

        # ---------- IMAGES ---------- #
        property_images = list(set([
            src
            for src in tree.xpath(
                "//div[contains(@class,'single-property-image-main')]//img/@src"
            )
        ]))

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath(
                "//div[contains(@class,'property-attachments')]//a/@href"
            )
        ]

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
            "agentCompanyName": "Ian Scott International",
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

    def extract_size(self, text):
        if not text:
            return "", ""

        SQM_TO_SQFT = 10.7639
        HECTARE_TO_ACRE = 2.47105

        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(r'(\d+(?:\.\d+)?)\s*(sq\.?\s*ft\.?|sqft|sf)\b', text)
        if m:
            size_ft = round(float(m.group(1)), 3)
            return size_ft, size_ac

        m = re.search(r'(\d+(?:\.\d+)?)\s*(sqm|m2|m²)\b', text)
        if m:
            size_ft = round(float(m.group(1)) * SQM_TO_SQFT, 3)
            return size_ft, size_ac

        m = re.search(r'(\d+(?:\.\d+)?)\s*(acres?|acre|ac)\b', text)
        if m:
            size_ac = round(float(m.group(1)), 3)
            return size_ft, size_ac

        m = re.search(r'(\d+(?:\.\d+)?)\s*(hectares?|hectare|ha)\b', text)
        if m:
            size_ac = round(float(m.group(1)) * HECTARE_TO_ACRE, 3)
            return size_ft, size_ac

        return size_ft, size_ac

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
        if not text:
            return ""
        text = text.upper()
        full_pattern = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        match = re.search(full_pattern, text)
        return match.group().strip() if match else ""

    def extract_price(self, text, sale_type=None):
        if not text or (sale_type and sale_type.lower() != "for sale"):
            return ""

        raw = text.lower().replace(",", "").replace("\u00a0", " ")

        prices = []
        for val in re.findall(r"£\s*(\d{5,})", raw):
            prices.append(float(val))

        million_matches = re.findall(
            r"(?:£\s*)?(\d+(?:\.\d+)?)\s*(million|m)\b",
            raw
        )
        for num, _ in million_matches:
            prices.append(float(num) * 1_000_000)

        if prices:
            return str(int(min(prices)))

        if any(x in raw for x in [
            "poa",
            "price on application",
            "upon application",
            "on application"
        ]):
            return ""

        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
