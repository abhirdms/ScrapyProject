import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class JemPropertyScraper:
    BASE_URL = "https://jemproperty.co.uk/sales/"
    DOMAIN = "https://jemproperty.co.uk"
    AGENT_COMPANY = "Jem Property"

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
                    "//div[@id='main-content']//article"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            articles = tree.xpath("//div[@id='main-content']//article")

            if not articles:
                break

            for article in articles:

                title = self._clean(" ".join(article.xpath(".//h3/text()")))

                # ✅ SKIP SOLD AT OUTER LEVEL
                if re.match(r'^\s*sold\b', title, re.I):
                    continue

                href = article.xpath(".//a[contains(@class,'btn-primary')]/@href")
                if not href:
                    continue

                url = urljoin(self.DOMAIN, href[0])

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
            "//h1[@class='h2 text-center']"
        )))

        tree = html.fromstring(self.driver.page_source)

        raw_title = self._clean(" ".join(
            tree.xpath("//h1[@class='h2 text-center']/text()")
        ))

        # ✅ Safety fallback (in case SOLD page accessed directly)
        if re.match(r'^\s*sold\b', raw_title, re.I):
            return None

        display_address = re.sub(r'£\s*[\d,]+.*', '', raw_title).strip(" ,")

        # ---------- SALE TYPE ---------- #
        sale_type_raw = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'justify-between')]/p[2]/text()")
        ))
        sale_type = self.normalize_sale_type(sale_type_raw)

        # ---------- PRICE ---------- #
        key_info_text = self._clean(" ".join(
            tree.xpath(
                "//span[normalize-space()='Key Information']"
                "/ancestor::div[contains(@class,'grid')]//p//text()"
            )
        ))

        price = self.extract_numeric_price(key_info_text, sale_type)

        # ---------- ALL STRUCTURED SECTIONS ---------- #
        sections = tree.xpath(
            "//aside[.//span[@class='h6' and normalize-space()!='']]"
        )

        section_texts = []

        for sec in sections:
            heading = " ".join(sec.xpath(".//span[@class='h6']/text()")).strip()
            content = " ".join(sec.xpath(".//p//text()")).strip()

            if heading and content:
                section_texts.append(f"{heading}: {content}")

        detailed_description = self._clean(" ".join(section_texts))

        # ---------- SIZE ---------- #
        size_source = key_info_text + " " + detailed_description
        size_ft, size_ac = self.extract_size(size_source)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- IMAGES ---------- #
        property_images = [
            src for src in tree.xpath("//picture//img/@src")
        ]

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
        ]

        return {
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
            "agentCompanyName": self.AGENT_COMPANY,
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }

    # ===================== HELPERS ===================== #

    def extract_size(self, text):
        if not text:
            return "", ""

        SQM_TO_SQFT = 10.7639
        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(r'(\d+(?:\.\d+)?)\s*(sqm|m2|m²)', text)
        if m:
            sqm = float(m.group(1))
            size_ft = round(sqm * SQM_TO_SQFT, 2)

        m = re.search(r'(\d+(?:\.\d+)?)\s*(sq\s*ft|sqft|sf)', text)
        if m:
            size_ft = float(m.group(1))

        m = re.search(r'(\d+(?:\.\d+)?)\s*(acres?|acre|ac)', text)
        if m:
            size_ac = float(m.group(1))

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale" or not text:
            return ""

        t = text.lower()

        if any(k in t for k in [
            "poa", "price on application", "upon application", "on application"
        ]):
            return ""

        if any(k in t for k in [
            "per annum", "pa", "pcm", "pw", "rent"
        ]):
            return ""

        m = re.search(r'£\s*(\d+(?:,\d{3})*(?:\.\d+)?)', t)
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
