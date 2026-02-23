import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class CommercialPropertyPartnersScraper:
    BASE_URL = "https://www.commercialpropertypartners.co.uk/property-search"
    DOMAIN = "https://www.commercialpropertypartners.co.uk"

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
            page_url = (
                self.BASE_URL
                if page == 1
                else f"{self.DOMAIN}/ev_property_residential_properties/search/page:{page}?property_type_id=&location="
            )

            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'card--properties')]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            listing_urls = tree.xpath(
                "//div[contains(@class,'card--properties')]"
                "//a[contains(@class,'card--properties-link')]/@href"
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
            "//div[contains(@class,'property-sidebar')]//h1"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'property-sidebar')]//h1/text()")
        ))

        # ---------- SALE TYPE ---------- #
        sale_type_raw = self._clean(" ".join(
            tree.xpath("//dt[contains(text(),'Tenure:')]/following-sibling::dd[1]/text()")
        ))
        sale_type = self.normalize_sale_type(sale_type_raw)

        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type = self._clean(" ".join(
            tree.xpath("//dt[contains(text(),'Property Type')]/following-sibling::dd[1]/text()")
        ))

        # ---------- SIZE ---------- #
        size_text = self._clean(" ".join(
            tree.xpath("//dt[contains(text(),'Size:')]/following-sibling::dd[1]/text()")
        ))
        size_ft, size_ac = self.extract_size(size_text)

        # ---------- PRICE BLOCK ---------- #
        price_block = self._clean(" ".join(
            tree.xpath("//dt[contains(text(),'Price:')]/following-sibling::dd[1]//text()")
        ))

        # Extract tenure (Leasehold / Freehold) from price block
        tenure = self.extract_tenure(price_block)

        # Price only if For Sale
        price = self.extract_numeric_price(price_block, sale_type)

        # ---------- DESCRIPTION ---------- #
        description_texts = tree.xpath(
            "//div[@class='row']//div[contains(@class,'col-md-8')]//text()"
        )
        detailed_description = self._clean(" ".join(description_texts))

        # ---------- IMAGES (exclude slick clones) ---------- #
        property_images = []
        image_srcs = tree.xpath(
            "//div[contains(@class,'slick-slide') "
            "and not(contains(@class,'slick-cloned'))]//img/@src"
        )
        for src in image_srcs:
            full = urljoin(self.DOMAIN, src)
            property_images.append(full)

        property_images = list(dict.fromkeys(property_images))

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath(
                "//div[contains(@class,'property-download')]"
                "//a[contains(@class,'btn--download')]/@href"
            )
        ]

        # ---------- AGENT (FIRST ONLY) ---------- #
        agent_names = tree.xpath(
            "//div[contains(@class,'col-md-4')]"
            "//h3[@class='text-dark']/text()"
        )
        agent_emails = tree.xpath(
            "//div[contains(@class,'col-md-4')]"
            "//a[starts-with(@href,'mailto:')]/@href"
        )
        agent_phones = tree.xpath(
            "//div[contains(@class,'col-md-4')]"
            "//a[starts-with(@href,'tel:')]/@href"
        )

        agent_name = self._clean(agent_names[0]) if agent_names else ""
        agent_email = agent_emails[0].replace("mailto:", "") if agent_emails else ""
        agent_phone = agent_phones[0].replace("tel:", "") if agent_phones else ""

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
            "agentCompanyName": "Commercial Property Partners",
            "agentName": agent_name,
            "agentCity": "",
            "agentEmail": agent_email,
            "agentPhone": agent_phone,
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
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\.?\s*ft|sqft|sf)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre)',
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
            "per annum", "pa", "pcm", "rent"
        ]):
            return ""

        m = re.search(r'[£]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?', t)
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
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""