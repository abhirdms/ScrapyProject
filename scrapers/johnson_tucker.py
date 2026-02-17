import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class JohnsonTuckerScraper:
    BASE_URLS = [
        "https://gfwllp.co.uk/residential-sales/",
        "https://gfwllp.co.uk/residential-lettings/",
        "https://gfwllp.co.uk/commercial-sales/",
        "https://gfwllp.co.uk/commercial-lettings/",
        "https://gfwllp.co.uk/farm-land-estates/",
        "https://gfwllp.co.uk/new-homes/",
    ]

    DOMAIN = "https://gfwllp.co.uk"

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

    # ================= RUN ================= #

    def run(self):

        for base in self.BASE_URLS:
            page = 1

            while True:
                page_url = base if page == 1 else f"{base}page/{page}/"
                self.driver.get(page_url)

                try:
                    self.wait.until(EC.presence_of_element_located((
                        By.XPATH,
                        "//a[contains(@class,'property-card')]"
                    )))
                except:
                    break

                tree = html.fromstring(self.driver.page_source)

                listing_urls = tree.xpath(
                    "//a[contains(@class,'property-card')]/@href"
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
                    except Exception as e:
                        print("Error:", e)
                        continue

                page += 1

        self.driver.quit()
        return self.results


    def parse_listing(self, url):

        self.driver.get(url)

        try:
            self.wait.until(EC.presence_of_element_located((
                By.XPATH,
                "//div[contains(@class,'bg-green')]"
            )))
        except:
            return None

        tree = html.fromstring(self.driver.page_source)

        # ---------- SALE TYPE FROM HERO DIV ---------- #
        sale_type_raw = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'bg-green')]//span[contains(@class,'term')]/text()")
        ))

        sale_type = self.normalize_sale_type(sale_type_raw)

        if sale_type in ["Sold", "Sold STC"]:
            return None

        # ---------- PRICE FROM SAME HERO DIV ---------- #
        price_text = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'bg-green')]"
                "//span[contains(@class,'font-bold') and contains(text(),'£')]/text()"
            )
        ))

        price = self.extract_numeric_price(price_text, sale_type)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//h1/text()")
        ))

        # ---------- PROPERTY TYPE FROM BREADCRUMB ---------- #
        property_sub_type = self._clean(" ".join(
            tree.xpath("//p[@id='breadcrumbs']//a[1]/text()")
        ))

        # ---------- DESCRIPTION ---------- #
        detailed_description = self._clean(" ".join(
            tree.xpath("//div[@data-expand-content]//text()")
        ))

        size_ft, size_ac = self.extract_size(detailed_description)
        tenure = self.extract_tenure(detailed_description)

        property_images = [
            img for img in tree.xpath("//img/@src")
            if img and "uploads" in img
        ]

        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
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
            "agentCompanyName": "Johnson Tucker",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }
        print("*****"*10)
        print(obj)
        print("*****"*10)


        return obj

    # ================= HELPERS ================= #

    def extract_numeric_price(self, text, sale_type):

        if not text:
            return ""

        if sale_type != "For Sale":
            return ""

        m = re.search(r'£\s*(\d+(?:,\d{3})*(?:\.\d+)?)', text)

        if not m:
            return ""

        return m.group(1).replace(",", "")

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        # ----- SQ FT variations -----
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|sf)',
            text
        )
        if m:
            size_ft = round(float(m.group(1)), 3)

        # ----- Acres variations -----
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:acres?|acre|ac)',
            text
        )
        if m:
            size_ac = round(float(m.group(1)), 3)

        return size_ft, size_ac


    def extract_tenure(self, text):
        text = text.lower()
        if "freehold" in text:
            return "Freehold"
        if "leasehold" in text:
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

        if "sold" in t:
            return "Sold STC"
        
        if "let agreed" in t:
            return "To Let"

        if "for sale" in t:
            return "For Sale"

        if "to let" in t:
            return "To Let"

        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
