import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class JimRawReesScraper:
    BASE_URL = "https://www.raw-rees.co.uk/property-listing/"
    DOMAIN = "https://www.raw-rees.co.uk"

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
                    "//div[@class='property-item-wrapper']/article"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            listing_urls = tree.xpath(
                "//div[@class='property-item-wrapper']/article//h4/a/@href"
            )

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
            "//h1[contains(@class,'page-title')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS (FROM ADDRESS TAG) ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//address[contains(@class,'title')]//text()")
        ))


        # ---------- SALE TYPE (METHOD DRIVEN) ---------- #
        status_text = self._clean(" ".join(
            tree.xpath("//span[contains(@class,'status-label')]/text()")
        ))

        price_raw = self._clean(" ".join(
            tree.xpath("//h5[contains(@class,'price')]//span[contains(@class,'price-and-type')]//text()")
        ))

        # ---------- DESCRIPTION ---------- #
        detailed_description = self._clean(" ".join(
            tree.xpath("//div[@class='content clearfix']//text()")
        ))

        sale_type_raw = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'wrap')]"
                "//span[contains(@class,'status-label')]/text()"
            )
        ))

        sale_type = self.normalize_sale_type(sale_type_raw)


        # ---------- PRICE (ONLY IF FOR SALE) ---------- #
        price = self.extract_numeric_price(price_raw, sale_type)

        # ---------- IMAGES (FULL SIZE) ---------- #
        property_images = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath(
                "//div[@id='property-slider-two-wrapper']"
                "//ul[@class='slides']//li/a/@href"
            )
            if href
        ]


        # ---------- SIZE ---------- #
        size_text = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'property-meta')]"
                "//span[@title='Area Size']/text()"
            )
        ))

        size_ft, size_ac = self.extract_size(size_text)

        # fallback to description if needed
        if not size_ft and not size_ac:
            size_ft, size_ac = self.extract_size(detailed_description)

        tenure = self.extract_tenure(detailed_description)


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
            "agentCompanyName": "Jim Raw Rees",
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


    def extract_postcode(self, text):
        if not text:
            return ""

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        t = text.upper()
        m = re.search(FULL, t) or re.search(PARTIAL, t)
        return m.group() if m else ""



    def extract_tenure(self, text):
        if not text:
            return ""

        t = text.lower()

        if "freehold" in t:
            return "Freehold"

        if "leasehold" in t:
            return "Leasehold"

        if "long leasehold" in t:
            return "Leasehold"

        return ""


    def extract_size(self, text):
        if not text:
            return "", ""

        # 🔥 CRITICAL FIX
        text = text.replace("\xa0", " ")  # handle &nbsp;
        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        # ---------- SQ FT ---------- #
        m = re.search(r'(\d+(?:\.\d+)?)\s*(sq\s*ft|sqft|sf)', text)
        if m:
            size_ft = round(float(m.group(1)), 3)

        # ---------- SQM (convert to sqft) ---------- #
        m = re.search(r'(\d+(?:\.\d+)?)\s*(sq\s*m|sqm|m2|m²)', text)
        if m:
            sqm = float(m.group(1))
            size_ft = round(sqm * 10.7639, 3)

        # ---------- ACRES ---------- #
        m = re.search(r'(\d+(?:\.\d+)?)\s*(acres?|acre|ac)', text)
        if m:
            size_ac = round(float(m.group(1)), 3)

        # ---------- HECTARES (convert to acres) ---------- #
        m = re.search(r'(\d+(?:\.\d+)?)\s*(hectares?|ha)', text)
        if m:
            hectares = float(m.group(1))
            size_ac = round(hectares * 2.47105, 3)

        return str(size_ft) if size_ft else "", str(size_ac) if size_ac else ""


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
            "pcm", "per month", "per week", "pw", "rent"
        ]):
            return ""

        m = re.search(r'[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)', text)
        if not m:
            return ""

        return m.group(1).replace(",", "")

    def normalize_sale_type(self, text):
        if not text:
            return "For Sale"

        t = text.lower()
        if any(k in t for k in ["for sale", "sale", "sold", "under offer"]):
            return "For Sale"

        if any(k in t for k in ["to let", "for rent", "rent", "letting" , 'let']):
            return "To Let"


        return "For Sale"


    def _clean(self, val):
        return " ".join(val.split()) if val else ""
