import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class HeaneyMicklethwaiteScraper:
    BASE_URL = "https://www.heaneymicklethwaite.co.uk/all_properties/"
    DOMAIN = "https://www.heaneymicklethwaite.co.uk"

    def __init__(self):
        self.results = []
        self.seen_urls = set()

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        service = Service("C:/Users/educa/Downloads/ScrapyProject/ScrapyProject/chromedriver.exe")
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 20)

    # ===================== RUN ===================== #

    def run(self):
        self.driver.get(self.BASE_URL)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'property-item')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        cards = tree.xpath("//div[contains(@class,'property-item')]")
        if not cards:
            self.driver.quit()
            return []

        for card in cards:
            try:
                obj = self.parse_card(card)
                if obj:
                    self.results.append(obj)
            except Exception:
                continue

        self.driver.quit()
        return self.results

    # ===================== CARD PARSER ===================== #

    def parse_card(self, card):

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            card.xpath(".//div[contains(@class,'property-info')]//h3/text()")
        ))

        # ---------- DESCRIPTION ---------- #
        description_parts = card.xpath(
            ".//div[contains(@class,'property-info')]//p//text()"
        )
        detailed_description = self._clean(" ".join(description_parts))

        # ---------- SIZE ---------- #
        size_text = self._clean(" ".join(
            card.xpath(".//p[contains(@class,'size')]/text()")
        ))
        size_ft, size_ac = self.extract_size(size_text)

        # ---------- PRICE ---------- #
        price = self.extract_price_from_text(detailed_description)

        # ---------- IMAGE ---------- #
        image = card.xpath(".//img/@src")
        property_images = [
            urljoin(self.DOMAIN, src) for src in image if src
        ]

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in card.xpath(".//a[contains(@href,'.pdf')]/@href")
        ]

        # ---------- SALE TYPE ---------- #
        sale_type = self.normalize_sale_type(detailed_description)

        obj = {
            "listingUrl": "",
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Heaney Micklethwaite",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": "",
            "saleType": sale_type,
        }

        print("*****" * 10)
        print(obj)
        print("*****" * 10)

        return obj

    # ===================== HELPERS ===================== #

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = text.replace("ft²", "sq ft")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf|square\s*feet)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac\.?)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        return size_ft, size_ac

    def extract_price_from_text(self, text):
        if not text:
            return ""

        t = text.lower()

        if any(k in t for k in [
            "poa", "price on application", "upon application", "on application"
        ]):
            return ""

        if any(k in t for k in [
            "per annum", "pa", "per year", "pcm",
            "per month", "pw", "per week", "rent"
        ]):
            return ""

        m = re.search(r'[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)', t)
        if not m:
            return ""

        return m.group(1).replace(",", "")

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
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""