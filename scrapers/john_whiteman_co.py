import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class JohnWhitemanCoScraper:
    BASE_URLS = {
        "For Sale": "https://www.jwandco.co.uk/property-for-sale.html",
        "To Let": "https://www.jwandco.co.uk/property-for-rent.html",
    }

    DOMAIN = "https://www.jwandco.co.uk"

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

        for sale_type, url in self.BASE_URLS.items():

            self.driver.get(url)

            self.wait.until(EC.presence_of_element_located((
                By.XPATH,
                "//div[@id='list']/div[@data-id]"
            )))

            tree = html.fromstring(self.driver.page_source)

            listing_urls = tree.xpath(
                "//div[@id='list']/div[@data-id]/a/@href"
            )

            for href in listing_urls:
                full_url = urljoin(self.DOMAIN, href)

                if full_url in self.seen_urls:
                    continue

                self.seen_urls.add(full_url)

                try:
                    obj = self.parse_listing(full_url, sale_type)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url, sale_type):

        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h1[contains(@class,'property-location')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//h1[contains(@class,'property-location')]/text()")
        ))

        # ---------- PRICE ---------- #
        price_text = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'property-price')]//text()")
        ))

        price = self.extract_numeric_price(price_text, sale_type)

        # ---------- DESCRIPTION ---------- #
        description = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'property-description')]//p//text()")
        ))

        bullets = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'property-bullets')]//text()")
        ))

        detailed_description = f"{description} {bullets}".strip()

        # ---------- SIZE (FROM DESCRIPTION) ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- IMAGES (FULL GALLERY) ---------- #

        page_source = self.driver.page_source

        image_matches = re.findall(
            r'\/assets\/components\/phpthumbof\/cache\/[^\"]+?\.(?:jpg|png)',
            page_source
        )


        property_images = list(set([
            urljoin(self.DOMAIN, img)
            for img in image_matches
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
            "brochureUrl": [],
            "agentCompanyName": "John Whiteman & Co",
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

        m = re.search(r'(\d+(?:\.\d+)?)\s*(sq\s*ft|sqft|sf)', text)
        if m:
            size_ft = round(float(m.group(1)), 3)

        m = re.search(r'(\d+(?:\.\d+)?)\s*(acres?|acre|ac)', text)
        if m:
            size_ac = round(float(m.group(1)), 3)

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

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
