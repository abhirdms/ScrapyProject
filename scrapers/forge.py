import re
from urllib.parse import urljoin

from lxml import html
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class ForgeScraper:
    LEASING_URL = "https://forge-cp.com/properties/leasing/"
    INVESTMENT_URL = "https://forge-cp.com/properties/investment/"
    DOMAIN = "https://forge-cp.com"

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

    def run(self):
        pages = [
            (self.LEASING_URL, "To Let"),
            (self.INVESTMENT_URL, "For Sale"),
        ]

        for page_url, default_sale_type in pages:
            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'lease_bdr')] | //div[contains(@class,'invest_status')]",
                )))
            except Exception:
                continue

            tree = html.fromstring(self.driver.page_source)

            if default_sale_type == "To Let":
                cards = tree.xpath(
                    "//div[contains(@class,'lease_list')]"
                    "//div[contains(@class,'row') and contains(@class,'lease_bdr')]"
                )
                for card in cards:
                    obj = self.parse_leasing_card(card, page_url, default_sale_type)
                    if obj:
                        self.results.append(obj)
            else:
                cards = tree.xpath(
                    "//section[contains(@class,'container')]"
                    "/div[contains(@class,'row') and contains(@class,'py-5')][.//div[contains(@class,'invest_status')]]"
                )
                for card in cards:
                    obj = self.parse_investment_card(card, page_url, default_sale_type)
                    if obj:
                        self.results.append(obj)

        self.driver.quit()
        return self.results

    def parse_leasing_card(self, card, page_url, default_sale_type):
        location = self._clean(" ".join(card.xpath(
            ".//div[contains(@class,'col-md-3') and contains(@class,'d-none') and contains(@class,'d-md-block')][1]//text()"
        )))
        address = self._clean(" ".join(card.xpath(
            ".//div[contains(@class,'col-md-4') and contains(@class,'col-8')][1]/text()"
        )))
        status_text = self._clean(" ".join(card.xpath(
            ".//div[contains(@class,'col-md-3') and contains(@class,'col-2')][1]//text()"
        )))

        if self.is_sold(status_text):
            return None

        sale_type = default_sale_type or self.normalize_sale_type(status_text)
        display_address = self._clean(", ".join([v for v in [address, location] if v]))

        brochure_urls = self._unique([
            urljoin(self.DOMAIN, href)
            for href in card.xpath(".//a[contains(translate(@href,'PDF','pdf'),'.pdf')]/@href")
            if href
        ])

        listing_url = brochure_urls[0] if brochure_urls else f"{page_url}#{self._slugify(display_address or status_text)}"
        if listing_url in self.seen_urls:
            return None
        self.seen_urls.add(listing_url)

        detailed_description = self._clean(" ".join([
            value for value in [location, address, status_text] if value
        ]))

        size_ft, size_ac = self.extract_size(detailed_description)
        tenure = self.extract_tenure(detailed_description)
        price = self.extract_numeric_price(detailed_description, sale_type)
        postcode = self.extract_postcode(display_address) or self.extract_postcode(detailed_description)
        obj = {
            "listingUrl": listing_url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": [],
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": postcode,
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Forge",
            "agentName": "",
            "agentCity": location,
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }

        return obj

    def parse_investment_card(self, card, page_url, default_sale_type):
        location = self._clean(" ".join(card.xpath(".//h1[contains(@class,'median')][1]//text()")))
        address = self._clean(" ".join(card.xpath(".//h4[1]//text()")))
        status_text = self._clean(" ".join(card.xpath(".//div[contains(@class,'invest_status')][1]//text()")))

        if self.is_sold(status_text):
            return None

        display_address = self._clean(", ".join([v for v in [address, location] if v]))

        terms_text = self._clean(" ".join(card.xpath(
            ".//div[contains(@class,'d-none') and contains(@class,'d-md-block')][1]//text()"
        )))

        sale_type = default_sale_type or self.normalize_sale_type(status_text)
        price = self.extract_numeric_price(terms_text, sale_type)

        brochure_urls = self._unique([
            urljoin(self.DOMAIN, href)
            for href in card.xpath(".//a[contains(translate(@href,'PDF','pdf'),'.pdf')]/@href")
            if href
        ])
        image_urls = self._unique([
            urljoin(self.DOMAIN, src)
            for src in card.xpath(".//div[contains(@class,'investment_image')]//img/@src")
            if src
        ])

        listing_url = brochure_urls[0] if brochure_urls else f"{page_url}#{self._slugify(display_address or status_text)}"
        if listing_url in self.seen_urls:
            return None
        self.seen_urls.add(listing_url)

        detailed_description = self._clean(" ".join([
            value for value in [location, address, status_text, terms_text] if value
        ]))

        size_ft, size_ac = self.extract_size(detailed_description)
        tenure = self.extract_tenure(detailed_description)
        postcode = self.extract_postcode(display_address) or self.extract_postcode(detailed_description)

        obj = {
            "listingUrl": listing_url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": image_urls,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": postcode,
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Forge",
            "agentName": "",
            "agentCity": location,
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }

        return obj 

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

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*feet)",
            text,
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        if not size_ft:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
                r"(sqm|sq\.?\s*m|m2|square\s*metres|square\s*meters)",
                text,
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm_value = min(a, b) if b else a
                size_ft = round(sqm_value * 10.7639, 3)

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(acres?|acre|ac\.?)",
            text,
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        if not size_ac:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
                r"(hectares?|ha)",
                text,
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
            "poa", "price on application", "upon application", "on application",
        ]):
            return ""

        if any(k in t for k in [
            "per annum", "pa", "per year", "pcm",
            "per month", "pw", "per week", "rent",
        ]):
            return ""

        m = re.search(r"[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?", t)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))
        if "m" in m.group(0):
            num *= 1_000_000

        return str(int(num))

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

        full_pattern = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b"
        partial_pattern = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\b"

        match = re.search(full_pattern, text)
        if match:
            return match.group().strip()

        match = re.search(partial_pattern, text)
        return match.group().strip() if match else ""

    def normalize_sale_type(self, text):
        t = text.lower() if text else ""
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t or "assignment" in t:
            return "To Let"
        return ""

    def is_sold(self, text):
        return "sold" in (text or "").lower()

    def _slugify(self, text):
        value = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
        return value or "property"

    def _unique(self, values):
        return list(dict.fromkeys(v for v in values if v))

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
