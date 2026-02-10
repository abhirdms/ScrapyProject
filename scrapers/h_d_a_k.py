import re
from urllib.parse import urljoin, urlparse, urlunparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class HDAKScraper:
    DOMAIN = "https://www.hdak.co.uk"

    SEARCH_URLS = {
        "Office": "https://www.hdak.co.uk/office-accommodation-preston.php?sort=desc",
        "Retail Unit": "https://www.hdak.co.uk/retail-units-preston.php?sort=desc",
        "Warehouse / Industrial": "https://www.hdak.co.uk/warehouse-to-let-preston.php?sort=desc",
        "Investment / Development": "https://www.hdak.co.uk/property-investment-preston.php?sort=desc",
    }

    def __init__(self):
        self.results = []
        self.seen_urls = set()

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"

        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        # ⚡ PERFORMANCE
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")
        chrome_options.add_argument("--disable-animations")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-software-rasterizer")

        service = Service("/usr/bin/chromedriver")
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 5)

    # ===================== RUN ===================== #

    def run(self):
        for property_subtype, base_url in self.SEARCH_URLS.items():
            page = 1

            while True:
                page_url = self._build_page_url(base_url, page)
                self.driver.get(page_url)

                try:
                    self.wait.until(EC.presence_of_element_located((
                        By.XPATH,
                        "//a[contains(@href,'viewproperty.php')]"
                    )))
                except Exception:
                    break

                tree = html.fromstring(self.driver.page_source)

                listing_urls = tree.xpath(
                    "//a[contains(@href,'viewproperty.php')]/@href"
                )
                if not listing_urls:
                    break

                for href in listing_urls:
                    url = urljoin(self.DOMAIN, href)

                    # ---------- DEDUPLICATION ---------- #
                    if url in self.seen_urls:
                        continue
                    self.seen_urls.add(url)

                    try:
                        self.results.append(
                            self.parse_listing(url, property_subtype)
                        )
                    except Exception:
                        continue

                page += 1

        self.driver.quit()
        return self.results

    # ===================== PAGINATION ===================== #

    def _build_page_url(self, base_url, page):
        if page == 1:
            return base_url

        parsed = urlparse(base_url)
        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            "",
            f"{parsed.query}&page={page}",
            ""
        ))

    # ===================== LISTING ===================== #

    def parse_listing(self, url, property_subtype):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'fullpropbottom')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'fullpropbottom')]//h1/text()")
        ))

        # ---------- DESCRIPTION ---------- #
        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'fullpropdesc')]"
                "//span[@class='desc']//text()"
            )
        ))

        # ---------- SALE TYPE ---------- #
        raw_sale_type = self._clean(" ".join(
            tree.xpath(
                "//span[@class='blocked' and contains(text(),'Availability')]"
                "/following-sibling::span[1]/text()"
            )
        ))

        if raw_sale_type.lower() == "for sale/let":
            sale_type = "For Sale"
        else:
            sale_type = raw_sale_type

        # ---------- PRICE (SALE TYPE DRIVEN) ---------- #
        raw_price = self._clean(" ".join(
            tree.xpath(
                "//span[@class='blocked' and contains(text(),'Price')]"
                "/following-sibling::span[1]/text()"
            )
        ))

        if sale_type == "For Sale":
            price = self.extract_price(raw_price)
        else:
            price = ""

        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- IMAGES ---------- #
        property_images = [
            urljoin(self.DOMAIN, src)
            for src in tree.xpath("//img[@data-image]/@data-image")
        ]

        # ---------- BROCHURE (ONLY GREEN BUTTON) ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath(
                "//div[contains(@class,'fullpropbottom')]"
                "//a[contains(@class,'btn-success') "
                "and contains(normalize-space(),'Download PDF')]/@href"
            )
        ]
        tenure = self.extract_tenure(detailed_description)

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_subtype,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "HDAK",
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

    def extract_price(self, text):
        if not text:
            return ""

        t = text.lower()
        if any(k in t for k in ["poa", "application", "pa", "pcm", "psf"]):
            return ""

        m = re.search(r'[£€]\s*(\d+(?:,\d{3})*)', t)
        return m.group(1).replace(",", "") if m else ""

    def extract_size(self, text):
        if not text:
            return "", ""

        t = text.lower().replace(",", "")
        t = re.sub(r"[–—−]", "-", t)

        size_ft = ""
        size_ac = ""

        ft = re.findall(
            r'(\d+(?:\.\d+)?)\s*(?:-\s*(\d+(?:\.\d+)?))?\s*(sq\s*ft|sqft|ft²)',
            t
        )
        if ft:
            size_ft = float(ft[0][0])

        ac = re.findall(
            r'(\d+(?:\.\d+)?)\s*(?:-\s*(\d+(?:\.\d+)?))?\s*(acres?|ac)',
            t
        )
        if ac:
            size_ac = float(ac[0][0])

        return size_ft, size_ac

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
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
