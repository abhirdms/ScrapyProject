import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class RafEstatesScraper:

    BASE_URLS = [
        "https://rafestates.com/property?category_type=commercial&category_type_id=0&ownership_type=leasehold&price_range%5B0%5D=0&price_range%5B1%5D=0&area_range%5B0%5D=0&area_range%5B1%5D=0",
        "https://rafestates.com/property?category_type=residential&category_type_id=0&ownership_type=lettings&price_range%5B0%5D=0&price_range%5B1%5D=0&bedroom_range%5B0%5D=0&bedroom_range%5B1%5D=0"
    ]

    DOMAIN = "https://rafestates.com"

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

        for base in self.BASE_URLS:
            page = 1

            while True:
                page_url = f"{base}&page={page}"
                self.driver.get(page_url)

                try:
                    self.wait.until(EC.presence_of_element_located((
                        By.XPATH,
                        "//div[@class='list-item']//div[contains(@class,'item')]"
                    )))
                except Exception:
                    break

                tree = html.fromstring(self.driver.page_source)

                listing_urls = tree.xpath(
                    "//div[@class='list-item']//div[contains(@class,'item')]/a/@href"
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

                page += 1

        self.driver.quit()
        return self.results


    # ===================== LISTING ===================== #

    def parse_listing(self, url):

        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[@id='show-content-details']"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//div[@class='tc_content']/p/text()")
        ))

        # ---------- TITLE / SUB TYPE ---------- #
        title_text = self._clean(" ".join(
            tree.xpath("//div[@class='tc_content']/h4/text()")
        ))

        property_sub_type = ""
        if "flat" in title_text.lower():
            property_sub_type = "Flat"
        elif "office" in title_text.lower():
            property_sub_type = "Office"

        # ---------- PRICE ---------- #
        price_raw = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'fp_price')]/text()")
        ))

        sale_type = self.normalize_sale_type(price_raw)

        # ---------- DESCRIPTION ---------- #
        detailed_description = self._clean(" ".join(
            tree.xpath("//div[@id='show-content-details']//text()")
        ))

        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- IMAGES ---------- #
        property_images = [
            src for src in tree.xpath(
                "//div[contains(@class,'spls_style_one')]//img/@src"
            ) if src
        ]

        # ---------- POSTCODE ---------- #
        postal_code = self.extract_postcode(display_address)

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price_raw,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": postal_code,
            "brochureUrl": [],
            "agentCompanyName": "Raf Estates",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": self.extract_tenure(detailed_description),
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
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\.?\s*ft|sqft|sf)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

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
        if "rent" in t or "let" in t:
            return "To Let"
        return ""


    def _clean(self, val):
        return " ".join(val.split()) if val else ""