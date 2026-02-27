import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class HartnellTaylorCookScraper:
    BASE_URL = "https://htc.uk.com/search/"
    DOMAIN = "https://htc.uk.com/"

    def __init__(self):
        self.results = []

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
            url = self.BASE_URL if page == 1 else f"{self.BASE_URL}page/{page}/"

            self.driver.get(url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH, "//ul[@class='properties clear']/li"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            listing_urls = tree.xpath(
                "//ul[@class='properties clear']/li"
                "//div[@class='thumbnail']/a/@href"
            )

            if not listing_urls:
                break

            for href in listing_urls:
                try:
                    self.results.append(self.parse_listing(href))
                except Exception:
                    continue

            page += 1

        self.driver.quit()
        return self.results

    # ================= LISTING ================= #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH, "//div[contains(@class,'propertySlider')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- BASIC FIELDS ---------- #

        


        display_address = self._clean(" ".join(
            tree.xpath("//p[@class='address']/text()")
        ))

        detailed_description = self._clean(" ".join(
            tree.xpath("//div[@class='description-contents']//p//text()")
        ))

        sale_type_raw = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'property-department')]//text()[normalize-space()]")
        ))

        price_text = self._clean(" ".join(
            tree.xpath("//span[@class='commercial-price']/text()")
        ))

        floor_text = " ".join(
            tree.xpath("//div[contains(@class,'floor-area')]//text()[normalize-space()]")
        )

        size_ft, size_ac = self.extract_size(floor_text)

        # ---------- IMAGES (SLICK – DEDUPED) ---------- #

        imgs = tree.xpath(
            "//div[contains(@class,'propertySlider')]"
            "//div[contains(@class,'slick-track')]//img/@src"
        )

        property_images = []
        seen = set()
        for img in imgs:
            img = img.strip()
            if img and img not in seen:
                seen.add(img)
                property_images.append(img)

        agent_name = ""
        agent_email = ""
        agent_phone = ""

        # 1️⃣ first agent NAME (HTC stable)
        name_nodes = tree.xpath("//p[contains(@class,'name-txt')]/text()")

        if name_nodes:
            agent_name = self._clean(name_nodes[0])

            # 2️⃣ FIRST email AFTER first agent name
            agent_email = self._clean(" ".join(
                tree.xpath(
                    "(//p[contains(@class,'name-txt')])[1]/following::a[starts-with(@href,'mailto:')][1]/text()"
                )
            ))

            # 3️⃣ FIRST phone AFTER first agent name
            agent_phone = self._clean(" ".join(
                tree.xpath(
                    "(//p[contains(@class,'name-txt')])[1]/following::a[starts-with(@href,'tel:')][1]/text()"
                )
            ))




        property_sub_type = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'property-type')]//text()[normalize-space()]"
            )
        ))

        features = [
            t.strip()
            for t in tree.xpath("//ul[contains(@class,'features')]/li/text()")
            if t.strip()
        ]

        brochure_urls = [
            self.normalize_url(href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
        ]

        # ---------- OBJECT ---------- #

        obj = {
            "listingUrl": url,

            "displayAddress": display_address,

            "price": self.extract_numeric_price(price_text, sale_type_raw),

            "propertySubType": property_sub_type,

            "propertyImage": property_images,

            "detailedDescription": detailed_description,

            "sizeFt": size_ft,
            "sizeAc": size_ac,

            "postalCode": self.extract_postcode(display_address),

            "brochureUrl": brochure_urls,

            "agentCompanyName": "Hartnell Taylor Cook",
            "agentName": agent_name,
            "agentEmail": agent_email,
            "agentPhone": agent_phone,
            "agentCity": "",
            "agentStreet": "",
            "agentPostcode": "",

            "tenure": self.get_tenure_from_features(features),

            "saleType": self.normalize_sale_type(sale_type_raw),
        }

        return obj

    # ================= HELPERS ================= #

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower()
        text = text.replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        # ---------- SQ FT (single or range) ----------
        sqft_pattern = (
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\s*ft|sqft|sf)'
        )
        m = re.search(sqft_pattern, text)
        if m:
            start = float(m.group(1))
            end = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(start, end), 3) if end else round(start, 3)

        # ---------- ACRES (single or range) ----------
        acre_pattern = (
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac)'
        )
        m = re.search(acre_pattern, text)
        if m:
            start = float(m.group(1))
            end = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(start, end) if end else start, 3)

        return size_ft, size_ac


    def extract_numeric_price(self, text, sale_type):
        if not text or "sale" not in sale_type.lower():
            return ""

        raw = text.lower()

        if any(k in raw for k in ["poa", "application"]):
            return ""

        raw = raw.replace("£", "").replace(",", "")
        nums = re.findall(r"\d+(?:\.\d+)?", raw)

        return str(int(float(nums[0]))) if nums else ""

    def extract_postcode(self, text):
        if not text:
            return ""

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        text = text.upper()
        m = re.search(FULL, text) or re.search(PARTIAL, text)
        return m.group() if m else ""

    def normalize_sale_type(self, text):
        t = text.lower()

        if "for sale" in t:
            return "For Sale"
        if "to let" in t:
            return "To Let"

        return ""

    def normalize_url(self, url):
        return urljoin(self.DOMAIN, url) if url else ""

    def get_tenure_from_features(self, features):

        if not features:
            return ""

        t = features.lower()

        if "freehold" in t:
            return "Freehold"

        if "leasehold" in t or "lease" in t:
            return "Leasehold"

        return ""


    def _clean(self, val):
        return val.strip() if val else ""
