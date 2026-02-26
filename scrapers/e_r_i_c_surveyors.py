import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class ERICSurveyorsScraper:
    BASE_URL = "https://www.ericsurveyors.com/shops-to-let"
    DOMAIN = "https://www.ericsurveyors.com"

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
            page_url = self.BASE_URL if page == 1 else self.BASE_URL
            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//section[contains(@class,'wixui-section')][.//h2]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            listing_blocks = tree.xpath(
                "//section[contains(@class,'wixui-section')][.//h2]"
            )

            if not listing_blocks:
                break

            for block in listing_blocks:
                href = block.xpath(".//h2//a/@href")
                if not href:
                    continue

                url = href[0]
                if not url.startswith("http"):
                    url = urljoin(self.DOMAIN, url)

                if url in self.seen_urls:
                    continue
                self.seen_urls.add(url)

                try:
                    obj = self.parse_listing(url, block)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

            break  # no pagination on wix grid

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url, block):

        # ---------- DISPLAY ADDRESS ---------- #
        # ---------- DISPLAY ADDRESS ---------- #
        raw_address = self._clean(" ".join(
            block.xpath(".//h2//text()")
        ))

        # Remove status words from address
        display_address = re.sub(
            r'\b(LET|SOLD|TO LET|UNDER OFFER)\b',
            '',
            raw_address,
            flags=re.IGNORECASE
        ).strip()

        # ---------- SALE TYPE (FROM TITLE TEXT) ---------- #
        sale_type = self.normalize_sale_type(display_address)
        if sale_type == "Sold":
            return None

        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type = ""

        # ---------- DESCRIPTION (NOT AVAILABLE ON GRID) ---------- #
        detailed_description = ""

        # ---------- SIZE (NOT AVAILABLE IN HTML) ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(detailed_description, sale_type)

        # ---------- IMAGE ---------- #
        property_images = [
            src for src in block.xpath(".//img/@src") if src
        ]

        # ---------- BROCHURE / LISTING URL ---------- #
        brochure_urls = []
        if url.lower().endswith(".pdf"):
            brochure_urls = [url]

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
            "agentCompanyName": "ERIC Surveyors",
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
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft|sqft|sf)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac)',
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
            "poa", "price on application", "upon application"
        ]):
            return ""

        if any(k in t for k in [
            "per annum", "pa", "pcm", "rent"
        ]):
            return ""

        m = re.search(r'[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?', t)
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

        full_pattern = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        partial_pattern = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        match = re.search(full_pattern, text)
        if match:
            return match.group().strip()

        match = re.search(partial_pattern, text)
        return match.group().strip() if match else ""

    def normalize_sale_type(self, text):
        t = text.lower()
        if "sold" in t:
            return "Sold"
        if "sale" in t:
            return "For Sale"
        if "let" in t:
            return "To Let"
        
        return "For Sale"

    def _clean(self, val):
        return " ".join(val.split()) if val else ""