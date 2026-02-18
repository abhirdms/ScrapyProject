import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

from lxml import html


class HummerstoneHawkinsScraper:
    BASE_URL = "https://hummerstonehawkins.com/search-results/?location=&commercial_property_type=&availability=&department=commercial"
    PAGE_URL = "https://hummerstonehawkins.com/search-results/page/{}/?location=&commercial_property_type=&availability=&department=commercial"
    DOMAIN = "https://hummerstonehawkins.com/"

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
        self.wait = WebDriverWait(self.driver, 15)

    # ===================== RUN ===================== #

    def run(self):
        page = 1

        while True:
            url = self.BASE_URL if page == 1 else self.PAGE_URL.format(page)
            self.driver.get(url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//ul[contains(@class,'properties')]/li"
                )))
            except TimeoutException:
                break

            tree = html.fromstring(self.driver.page_source)

            listings = tree.xpath("//ul[contains(@class,'properties')]/li")
            if not listings:
                break

            for listing in listings:

                rel = listing.xpath(".//div[@class='propertySummaryWrapper']/h3/a/@href")
                if not rel:
                    continue

                full_url = urljoin(self.DOMAIN, rel[0])

                if full_url in self.seen_urls:
                    continue
                self.seen_urls.add(full_url)

                # -------- SALE TYPE FROM <li> CLASS -------- #
                sale_type = self.get_sale_type_from_listing(listing)


                try:
                    obj = self.parse_listing(full_url, sale_type)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

            page += 1

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url, sale_type):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h1[contains(@class,'property_title')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//h1[contains(@class,'property_title')]/text()")
        ))

        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type = self._clean(" ".join(
            tree.xpath("//li[@class='property-type']/text()")
        ))

        # ---------- DESCRIPTION ---------- #

        features = tree.xpath("//div[@class='features']//li/text()")

        summary = tree.xpath(
            "//div[@class='summary'][.//h4[contains(text(),'Property Summary')]]"
            "//text()[not(ancestor::script)]"
        )

        # Remove leaflet / map junk manually
        clean_summary = []
        for s in summary:
            s = s.strip()
            if not s:
                continue
            if "leaflet" in s.lower():
                continue
            if "var property_map" in s.lower():
                continue
            if "function initialize_property_map" in s.lower():
                continue
            clean_summary.append(s)

        detailed_description = self._clean(" ".join(features + clean_summary))


        # ---------- SIZE ---------- #
        floor_area_text = self._clean(" ".join(
            tree.xpath("//div[@class='floor-area']/text()")
        ))

        size_ft, size_ac = self.extract_size(floor_area_text)

        # ---------- PRICE (ONLY IF FOR SALE) ---------- #
        price = self.extract_price(tree) if sale_type == "For Sale" else ""

        # ---------- IMAGES ---------- #
        property_images = list(set(
            tree.xpath("//a[contains(@class,'propertyhive-main-image')]/img/@src")
        ))

        # ---------- BROCHURE ---------- #
        brochure_urls = tree.xpath(
            "//li[@class='action-brochure']/a/@href"
        )

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
            "agentCompanyName": "Hummerstone & Hawkins",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": self.extract_tenure(detailed_description),
            "saleType": sale_type,
        }


        return obj

    # ===================== HELPERS ===================== #

    def extract_price(self, tree):
        sale = tree.xpath("//span[@class='commercial-price']/text()")
        rent = tree.xpath("//span[@class='commercial-rent']/text()")

        text = sale[0] if sale else rent[0] if rent else ""

        if not text:
            return ""

        text = text.replace("£", "").replace(",", "")
        numbers = re.findall(r"\d+(?:\.\d+)?", text)

        return numbers[0] if numbers else ""

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(r"(\d+(?:\.\d+)?)\s*(sq\s*ft|sqft)", text)
        if m:
            size_ft = int(float(m.group(1)))

        m = re.search(r"(\d+(?:\.\d+)?)\s*(acre|acres)", text)
        if m:
            size_ac = float(m.group(1))

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
    
    def get_sale_type_from_listing(self, listing):
        li_class = " ".join(listing.xpath("./@class")).lower()

        if "availability-for-sale" in li_class or 'sale' in li_class:
            return "For Sale"

        if "availability-to-let" in li_class or 'let' in li_class:
            return "To Let"

        if "availability-under-offer" in li_class or 'under-offer' in li_class:
            return "For Sale"

        return ""


    def _clean(self, val):
        return re.sub(r"\s+", " ", val).strip() if val else ""
