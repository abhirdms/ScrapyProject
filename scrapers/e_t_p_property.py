import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class ETPPropertyScraper:
    BASE_URL = "https://www.cs-re.co.uk/properties/"
    DOMAIN = "https://www.cs-re.co.uk"

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
            "//article[contains(@class,'property-block')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listings = tree.xpath("//article[contains(@class,'property-block')]")

        for listing in listings:

            href = listing.xpath(".//a[contains(@class,'title')]/@href")
            if not href:
                continue

            url = urljoin(self.DOMAIN, href[0])

            if url in self.seen_urls:
                continue
            self.seen_urls.add(url)

            # -------- OUTER PAGE EXTRACTION -------- #

            size_text = self._clean(" ".join(
                listing.xpath(
                    ".//img[contains(@src,'size-ico')]"
                    "/following-sibling::span//text()"
                )
            ))

            price_text = self._clean(" ".join(
                listing.xpath(
                    ".//img[contains(@src,'price-ico')]"
                    "/following-sibling::span//text()"
                )
            ))

            property_sub_type = self._clean(" ".join(
                listing.xpath(
                    ".//img[contains(@src,'business-type-ico')]"
                    "/following-sibling::span/text()"
                )
            ))

            tenure = self._clean(" ".join(
                listing.xpath(
                    ".//img[contains(@src,'freehol-ico')]"
                    "/following-sibling::span/text()"
                )
            ))

            brochure_urls = [
                urljoin(self.DOMAIN, b)
                for b in listing.xpath(
                    ".//a[contains(@class,'brochure-button')]/@href"
                )
            ]

            size_ft, size_ac = self.extract_size(size_text)

            # Determine sale type from price text
            sale_type = self.normalize_sale_type(price_text)

            price = self.extract_numeric_price(price_text, sale_type)

            try:
                obj = self.parse_listing(
                    url,
                    size_ft,
                    size_ac,
                    price,
                    property_sub_type,
                    tenure,
                    brochure_urls,
                    sale_type
                )
                if obj:
                    self.results.append(obj)
            except Exception:
                continue

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url, size_ft, size_ac,
                      price, property_sub_type,
                      tenure, brochure_urls, sale_type):

        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h1[contains(@class,'h1')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        display_address = self._clean(" ".join(
            tree.xpath("//h1[contains(@class,'h1')]/text()")
        ))

        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'description')]//p//text()"
            )
        ))

        property_images = [
            src for src in tree.xpath(
                "//div[contains(@class,'slider-photos')]//img/@src"
            ) if src
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
            "agentCompanyName": "ETP Property",
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

        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf)',
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

    def normalize_sale_type(self, text):
        if not text:
            return ""

        t = text.lower()
        if "per annum" in t or "per sq ft" in t:
            return "To Let"
        if "£" in t and "per" not in t:
            return "For Sale"
        return "To Let"

    def extract_postcode(self, text: str):
        if not text:
            return ""

        text = text.upper()

        full_pattern = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        match = re.search(full_pattern, text)
        return match.group().strip() if match else ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""