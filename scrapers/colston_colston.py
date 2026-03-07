import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class ColstonColstonScraper:
    START_URL = "https://www.cs-re.co.uk/properties/"
    ROOT_DOMAIN = "https://www.cs-re.co.uk"

    def __init__(self):
        self.collected_data = []
        self.visited_links = set()

        chrome_opts = Options()
        chrome_opts.binary_location = "/usr/bin/chromium-browser"
        chrome_opts.add_argument("--headless=new")
        chrome_opts.add_argument("--no-sandbox")
        chrome_opts.add_argument("--disable-dev-shm-usage")
        chrome_opts.add_argument("--window-size=1920,1080")

        service = Service("/usr/bin/chromedriver")
        self.browser = webdriver.Chrome(service=service, options=chrome_opts)
        self.waiter = WebDriverWait(self.browser, 20)

    # ===================== EXECUTION ===================== #

    def run(self):
        self.browser.get(self.START_URL)

        self.waiter.until(EC.presence_of_element_located((
            By.XPATH,
            "//article[contains(@class,'property-block')]"
        )))

        dom_tree = html.fromstring(self.browser.page_source)

        property_cards = dom_tree.xpath("//article[contains(@class,'property-block')]")

        for card in property_cards:

            link = card.xpath(".//a[contains(@class,'title')]/@href")
            if not link:
                continue

            property_url = urljoin(self.ROOT_DOMAIN, link[0])

            if property_url in self.visited_links:
                continue
            self.visited_links.add(property_url)

            # -------- LIST PAGE DATA -------- #

            size_raw = self.clean_text(" ".join(
                card.xpath(
                    ".//img[contains(@src,'size-ico')]"
                    "/following-sibling::span//text()"
                )
            ))

            price_raw = self.clean_text(" ".join(
                card.xpath(
                    ".//img[contains(@src,'price-ico')]"
                    "/following-sibling::span//text()"
                )
            ))

            subtype = self.clean_text(" ".join(
                card.xpath(
                    ".//img[contains(@src,'business-type-ico')]"
                    "/following-sibling::span/text()"
                )
            ))

            tenure_info = self.clean_text(" ".join(
                card.xpath(
                    ".//img[contains(@src,'freehol-ico')]"
                    "/following-sibling::span/text()"
                )
            ))

            brochure_links = [
                urljoin(self.ROOT_DOMAIN, b)
                for b in card.xpath(
                    ".//a[contains(@class,'brochure-button')]/@href"
                )
            ]

            sqft, acres = self.parse_size(size_raw)

            transaction_type = self.detect_sale_type(price_raw)

            numeric_price = self.parse_price(price_raw, transaction_type)

            try:
                record = self.scrape_detail_page(
                    property_url,
                    sqft,
                    acres,
                    numeric_price,
                    subtype,
                    tenure_info,
                    brochure_links,
                    transaction_type
                )
                if record:
                    self.collected_data.append(record)
            except Exception:
                continue

        self.browser.quit()
        return self.collected_data

    # ===================== DETAIL PAGE ===================== #

    def scrape_detail_page(self, property_url, sqft, acres,
                           numeric_price, subtype,
                           tenure_info, brochure_links, transaction_type):

        self.browser.get(property_url)

        self.waiter.until(EC.presence_of_element_located((
            By.XPATH,
            "//h1[contains(@class,'h1')]"
        )))

        dom_tree = html.fromstring(self.browser.page_source)

        address = self.clean_text(" ".join(
            dom_tree.xpath("//h1[contains(@class,'h1')]/text()")
        ))

        description = self.clean_text(" ".join(
            dom_tree.xpath(
                "//div[contains(@class,'description')]//p//text()"
            )
        ))

        images = [
            img for img in dom_tree.xpath(
                "//div[contains(@class,'slider-photos')]//img/@src"
            ) if img
        ]

        data_obj = {
            "listingUrl": property_url,
            "displayAddress": address,
            "price": numeric_price,
            "propertySubType": subtype,
            "propertyImage": images,
            "detailedDescription": description,
            "sizeFt": sqft,
            "sizeAc": acres,
            "postalCode": self.find_postcode(address),
            "brochureUrl": brochure_links,
            "agentCompanyName": "Colston & Colston",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure_info,
            "saleType": transaction_type,
        }

        return data_obj

    # ===================== UTILITIES ===================== #

    def parse_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        sqft = ""
        acres = ""

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            sqft = round(min(a, b), 3) if b else round(a, 3)

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac\.?)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            acres = round(min(a, b), 3) if b else round(a, 3)

        return sqft, acres

    def parse_price(self, text, transaction_type):
        if transaction_type != "For Sale":
            return ""

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

        num = float(m.group(1).replace(",", ""))
        return str(int(num))

    def detect_sale_type(self, text):
        if not text:
            return ""

        t = text.lower()
        if "per annum" in t or "per sq ft" in t:
            return "To Let"
        if "£" in t and "per" not in t:
            return "For Sale"
        return ""

    def find_postcode(self, text: str):
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

    def clean_text(self, val):
        return " ".join(val.split()) if val else ""