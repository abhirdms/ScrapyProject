import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class LofthouseAndPartnersScraper:
    BASE_URL = "https://lofthouseandpartners.co.uk/property-search/#results"
    DOMAIN = "https://lofthouseandpartners.co.uk"

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
            '//article[contains(@class,"type-property")]'
        )))

        # ================= LOAD MORE LOOP ================= #
        while True:
            try:
                articles_before = len(self.driver.find_elements(
                    By.XPATH,
                    '//article[contains(@class,"type-property")]'
                ))

                load_more_btn = self.driver.find_element(By.ID, "wpas-load-btn")

                if not load_more_btn.is_displayed():
                    break

                self.driver.execute_script("arguments[0].click();", load_more_btn)

                # Wait until new articles are loaded
                self.wait.until(lambda d: len(d.find_elements(
                    By.XPATH,
                    '//article[contains(@class,"type-property")]'
                )) > articles_before)

            except Exception:
                break
        # ================================================== #

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            '//article[contains(@class,"type-property")]'
            '//h3[contains(@class,"entry-title")]/a/@href'
        )

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

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            '//h1[@class="entry-title"]'
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath('//h1[@class="entry-title"]/text()')
        ))

        # ---------- PRICE ---------- #
        price_raw = self._clean(" ".join(
            tree.xpath(
                '//dt[normalize-space()="Price"]/following-sibling::dd[1]/text()'
            )
        ))

        sale_type = self.normalize_sale_type(price_raw)
        price = self.extract_numeric_price(price_raw, sale_type)

        # ---------- PROPERTY TYPE ---------- #
        property_sub_type = ", ".join(
            tree.xpath(
                '//dt[normalize-space()="Categories"]'
                '/following-sibling::dd[1]//span/text()'
            )
        )

        # ---------- DESCRIPTION ---------- #
        detailed_description = self._clean(" ".join(
            tree.xpath(
                '//div[contains(@class,"entry-content")]//ul/li//text()'
            )
        ))

        # ---------- SIZE (FROM DESCRIPTION) ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- TENURE (FROM DESCRIPTION) ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- IMAGE ---------- #
        property_images = [
            urljoin(self.DOMAIN, src)
            for src in tree.xpath(
                '//aside[contains(@class,"sidebar")]//img/@src'
            )
        ]

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href.strip())
            for href in tree.xpath(
                '//aside[contains(@class,"sidebar")]'
                '//a[contains(@href,".pdf")]/@href'
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
            "agentCompanyName": "Lofthouse and Partners",
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

        # ---- SQ FT ----
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\.?\s*ft\.?|sqft|ft2|ft²|sf)\b',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        # ---- SQM ----
        if not size_ft:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sqm|m2|m²)',
                text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm_val = min(a, b) if b else a
                size_ft = round(sqm_val * SQM_TO_SQFT, 3)

        # ---- ACRES ----
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac)\b',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        # ---- HECTARES ----
        if not size_ac:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(hectares?|ha)\b',
                text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                ha_val = min(a, b) if b else a
                size_ac = round(ha_val * HECTARE_TO_ACRE, 3)

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

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale":
            return ""

        if not text:
            return ""

        t = text.lower()

        # Ignore POA types
        if any(k in t for k in [
            "poa", "price on application", "upon application", "on application"
        ]):
            return ""

        # 🔥 IMPORTANT FIX:
        # Only extract the part BEFORE "or to let"
        sale_part = t.split("or to let")[0]

        # Remove VAT text
        sale_part = sale_part.replace("plus vat", "")

        # Find first £ amount in sale portion
        m = re.search(r'£\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?', sale_part)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))

        # Handle million shorthand
        if "m" in m.group(0):
            num *= 1_000_000

        return str(int(num))

    def extract_postcode(self, text):
        if not text:
            return ""

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        t = text.upper()
        m = re.search(FULL, t) or re.search(PARTIAL, t)
        return m.group() if m else ""

    def normalize_sale_type(self, text):
        t = text.lower()
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
