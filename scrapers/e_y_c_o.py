import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class EYCOScraper:
    BASE_URL = "https://www.eyco.co.uk/search/?property-type=&sale-rent=&town=&keyword=&min-size=&max-size=&min-price=&max-price=&view=table"
    DOMAIN = "https://www.eyco.co.uk"

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
            page_url = f"{self.BASE_URL}&pg={page}"
            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'property-search__results--table')]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            # ---------- DIRECT PROPERTY ROWS ---------- #
            direct_urls = tree.xpath(
                "//div[contains(@class,'property-search__results--table')]"
                "//tbody/tr[@data-url and not(@data-scheme)]/@data-url"
            )

            # ---------- NESTED SCHEME PROPERTY ROWS ---------- #
            nested_urls = tree.xpath(
                "//tr[contains(@class,'scheme-properties')]"
                "//tr[@data-url]/@data-url"
            )

            listing_urls = direct_urls + nested_urls

            if not listing_urls:
                break

            for href in listing_urls:
                url = urljoin(self.DOMAIN, href)

                if url in self.seen_urls:
                    continue
                self.seen_urls.add(url)

                try:
                    obj = self.parse_listing(url)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

            page += 1

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//section[contains(@class,'scheme__overview')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//section[contains(@class,'scheme__overview')]//h1/text()")
        ))

        # ---------- SALE TYPE ---------- #
        sale_type_raw = self._clean(" ".join(
            tree.xpath(
                "//h2[normalize-space()='Availability']/following-sibling::p[1]/text()"
            )
        ))

        sale_type = self.normalize_sale_type(sale_type_raw)

        # ---------- DESCRIPTION ---------- #
        description = self._clean(" ".join(
            tree.xpath(
                "//h2[normalize-space()='Description']/following-sibling::p[1]//text()"
            )
        ))

        location = self._clean(" ".join(
            tree.xpath(
                "//h2[normalize-space()='Location']/following-sibling::p[1]//text()"
            )
        ))

        key_points = self._clean(" ".join(
            tree.xpath(
                "//h2[normalize-space()='Key Points']/following-sibling::ul[1]//li//text()"
            )
        ))

        detailed_description = " ".join(
            part for part in [description, location, key_points] if part
        )

        # ---------- SIZE (SIZE SECTION + DESCRIPTION) ---------- #
        size_section = self._clean(" ".join(
            tree.xpath(
                "//h2[normalize-space()='Size']/following-sibling::p[1]//text()"
            )
        ))

        combined_size_text = " ".join([size_section, detailed_description])

        size_ft, size_ac = self.extract_size(combined_size_text)

        # ---------- TENURE ---------- #
        lease_type = self._clean(" ".join(
            tree.xpath(
                "//h2[normalize-space()='Lease Type']/following-sibling::p[1]/text()"
            )
        ))

        tenure = self.extract_tenure(lease_type + " " + detailed_description)

        # ---------- PRICE ---------- #
        price_text = self._clean(" ".join(
            tree.xpath(
                "//h2[normalize-space()='Rent']/following-sibling::p[1]/text()"
            )
        ))

        price = self.extract_numeric_price(price_text + " " + detailed_description, sale_type)

        # ---------- IMAGES ---------- #
        property_images = tree.xpath(
            "//section[contains(@class,'scheme__overview')]"
            "/preceding-sibling::div[contains(@class,'wrapper')][1]"
            "//img/@src"
        )

        property_images = [
            src for src in property_images
            if src
            and src.startswith("https://neo.completelyretail.co.uk/")
        ]
        # ---------- BROCHURE ---------- #
        brochure_urls = list(set([
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
        ]))

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "EYCO",
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

        text = text.lower()
        text = text.replace(",", "")
        text = text.replace("ft²", "sq ft")
        text = text.replace("m²", "sqm")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        # SQUARE FEET
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft|sqft|sf|square\s*feet)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        # SQUARE METRES
        if not size_ft:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(sqm|sq\.?\s*m|m2)',
                text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm_value = min(a, b) if b else a
                size_ft = round(sqm_value * 10.7639, 3)

        # ACRES
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac\.?)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        # HECTARES
        if not size_ac:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(hectares?|ha)',
                text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                hectare_value = min(a, b) if b else a
                size_ac = round(hectare_value * 2.47105, 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale":
            return ""

        if not text:
            return ""

        t = text.lower()

        if any(k in t for k in [
            "poa", "price on application", "upon application", "on application"
        ]):
            return ""

        m = re.search(r'[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)', t)
        if not m:
            return ""

        return str(int(float(m.group(1).replace(",", ""))))

    def extract_tenure(self, text):
        if not text:
            return ""

        t = text.lower()
        if "freehold" in t:
            return "Freehold"
        if "leasehold" in t:
            return "Leasehold"
        return ""

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

    def normalize_sale_type(self, text):
        t = text.lower()
        if "sale" in t or "for sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""