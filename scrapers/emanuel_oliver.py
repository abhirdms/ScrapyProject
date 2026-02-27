import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class EmanuelOliverScraper:
    BASE_URL = "https://emanueloliver.com/properties/"
    DOMAIN = "https://emanueloliver.com"

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
            page_url = self.BASE_URL
            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//table[contains(@class,'properties-table')]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            listing_urls = tree.xpath(
                "//table[contains(@class,'properties-table')]"
                "//tr[contains(@class,'property-row')]//td[2]//a/@href"
            )

            if not listing_urls:
                break

            for href in listing_urls:
                url = href if href.startswith("http") else urljoin(self.DOMAIN, href)

                if url in self.seen_urls:
                    continue
                self.seen_urls.add(url)

                try:
                    obj = self.parse_listing(url)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

            break  # single page only

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url):
        # Page already contains all data in table.
        # We reload base page and find row by URL.

        self.driver.get(self.BASE_URL)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//table[contains(@class,'properties-table')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        row = tree.xpath(
            f"//tr[contains(@class,'property-row')]"
            f"[.//a[@href='{url}']]"
        )

        if not row:
            return None

        row = row[0]

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            row.xpath("./td[2]//a/text()")
        ))

        # ---------- TOWN ---------- #
        town = self._clean(" ".join(
            row.xpath("./td[1]/text()")
        ))

        # ---------- SALE TYPE (HELPER-DRIVEN) ---------- #
        sale_type_raw = self._clean(" ".join(
            row.xpath("./td[3]//text()")
        ))

        sale_type = self.normalize_sale_type(sale_type_raw)

        # ---------- DETAILED DESCRIPTION ---------- #
        detailed_description = sale_type_raw

        # ---------- SIZE (FROM TABLE CELL TEXT) ---------- #
        # ---------- SIZE (GROUND FLOOR = SQFT DIRECT VALUE) ---------- #
        size_text = self._clean(" ".join(
            row.xpath("./td[4]//text()")
        ))

        size_ft = ""
        size_ac = ""

        if size_text and "various" not in size_text.lower():
            cleaned = size_text.replace(",", "")
            cleaned = re.sub(r"[–—−]", "-", cleaned)

            # Handle range like "1560 - 1830"
            match = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?", cleaned)
            if match:
                a = float(match.group(1))
                b = float(match.group(2)) if match.group(2) else None
                size_ft = str(int(min(a, b))) if b else str(int(a))

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- PRICE (ONLY IF FOR SALE) ---------- #
        price = self.extract_numeric_price(detailed_description, sale_type)

        # ---------- BROCHURE ---------- #
        brochure_urls = [url]

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": [],
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Emanuel Oliver",
            "agentName": "",
            "agentCity": town,
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

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*feet)',
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

        m = re.search(r'[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)', t)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))
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
        return "To Let"


    def _clean(self, val):
        return " ".join(val.split()) if val else ""