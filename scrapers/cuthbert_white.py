import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class CuthbertWhiteScraper:
    BASE_URL = "https://cuthbertwhite.com/properties"
    DOMAIN = "https://cuthbertwhite.com"

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
        self.driver.get(self.BASE_URL)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//article[contains(@class,'portfolio-item')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_cards = tree.xpath("//article[contains(@class,'portfolio-item')]")

        for card in listing_cards:
            href = self._clean(" ".join(card.xpath(".//h3/a/@href")))
            if not href:
                continue

            url = urljoin(self.DOMAIN, href)

            if url in self.seen_urls:
                continue
            self.seen_urls.add(url)

            listing_meta = {
                "title": self._clean(" ".join(card.xpath(".//h3/a/text()"))),
                "subtitle": self._clean(" ".join(card.xpath(".//div[contains(@class,'portfolio-desc')]//span/text()"))),
                "status": self._clean(" ".join(card.xpath(".//div[contains(@class,'status')]//p/text()"))),
            }

            try:
                obj = self.parse_listing(url, listing_meta)
                if obj:
                    self.results.append(obj)
            except Exception:
                continue

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url, listing_meta=None):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'row')]"
        )))

        tree = html.fromstring(self.driver.page_source)
        listing_meta = listing_meta or {}
        page_text = self._clean(" ".join(tree.xpath("//body//text()")))

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath(
                "//div[@class='page-title-text']/h1/text()"
                " | //h1/text()"
                " | //meta[@property='og:title']/@content"
            )
        ))
        if not display_address:
            display_address = listing_meta.get("title", "")

        # ---------- SALE TYPE ---------- #
        sale_type_raw = self._clean(" ".join(
            tree.xpath(
                "//div[@class='page-title-text']//span/text()"
                " | //div[contains(@class,'page-subtitle')]//text()"
            )
        ))
        sale_type_hints = " ".join(filter(None, [
            sale_type_raw,
            listing_meta.get("subtitle", ""),
            listing_meta.get("status", ""),
            page_text,
        ]))
        sale_type = self.normalize_sale_type(sale_type_hints)

        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(sale_type_hints, sale_type)
        if not price:
            price_text = self._clean(" ".join(
                tree.xpath(
                    "//li/strong[contains(text(),'Offers')]/text()"
                    " | //li[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'offers')]//text()"
                )
            ))
            price = self.extract_numeric_price(price_text, "For Sale")

        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type = self.extract_property_sub_type(" ".join(filter(None, [
            listing_meta.get("subtitle", ""),
            page_text,
        ])))

        # ---------- DESCRIPTION ---------- #
        description_parts = tree.xpath(
            "//div[contains(@class,'col-content')]"
            "//div[contains(@class,'ccm-custom-style-container')]//p//text()"
        )
        detailed_description = self._clean(" ".join(description_parts))

        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(" ".join([detailed_description, page_text]))

        for raw_sqft in tree.xpath("//table//tr[position()>1]/td[2]//text()"):
            value = self._clean(raw_sqft).replace(",", "")
            m = re.search(r"\d+(?:\.\d+)?", value)
            if not m:
                continue
            sqft_value = round(float(m.group()), 3)
            if not size_ft or sqft_value < size_ft:
                size_ft = sqft_value

        for raw_sqm in tree.xpath("//table//tr[position()>1]/td[3]//text()"):
            value = self._clean(raw_sqm).replace(",", "")
            m = re.search(r"\d+(?:\.\d+)?", value)
            if not m:
                continue
            sqft_value = round(float(m.group()) * 10.7639, 3)
            if not size_ft or sqft_value < size_ft:
                size_ft = sqft_value

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(" ".join([detailed_description, page_text]))

        # ---------- IMAGES ---------- #
        images = tree.xpath(
            "//div[contains(@class,'flexslider')]"
            "//div[contains(@class,'slide') and not(contains(@class,'clone'))]"
            "//img/@src"
        )
        property_images = []
        for img in images:
            absolute_img = urljoin(self.DOMAIN, img)
            if absolute_img and absolute_img not in property_images:
                property_images.append(absolute_img)

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath(
                "//a[contains(@href,'download_file')]/@href"
                " | //a[contains(@href,'.pdf')]/@href"
            )
        ]

        # ---------- AGENT DETAILS ---------- #
        agent_name = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'call-agent')]/h5/text()")
        ))

        agent_email = tree.xpath("//a[starts-with(@href,'mailto:')]/@href")
        agent_email = agent_email[0].replace("mailto:", "") if agent_email else ""

        agent_phone = tree.xpath(
            "//div[contains(@class,'call-agent')]//a[starts-with(@href,'tel:')]/@href"
        )
        agent_phone = agent_phone[0].replace("tel:", "").strip() if agent_phone else ""

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
            "agentCompanyName": "CuthbertWhite",
            "agentName": agent_name,
            "agentCity": "",
            "agentEmail": agent_email,
            "agentPhone": agent_phone,
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
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

        text = text.lower()
        text = text.replace(",", "")
        text = text.replace("ft²", "sq ft")
        text = text.replace("m²", "sqm")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*feet)",
            text,
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        if not size_ft:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
                r"(sqm|sq\.?\s*m|m2|square\s*metres|square\s*meters)",
                text,
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm_value = min(a, b) if b else a
                size_ft = round(sqm_value * 10.7639, 3)

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(acres?|acre|ac\.?)",
            text,
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        if not size_ac:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
                r"(hectares?|ha)",
                text,
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                hectare_value = min(a, b) if b else a
                size_ac = round(hectare_value * 2.47105, 3)

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

        m = re.search(r"[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?", t)
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

        full_pattern = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b"
        partial_pattern = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\b"

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

    def extract_property_sub_type(self, text):
        if not text:
            return ""

        t = text.lower()
        mapping = [
            ("office", "Office"),
            ("retail", "Retail"),
            ("industrial", "Industrial"),
            ("land", "Land"),
            ("leisure", "Leisure"),
            ("investment", "Investment"),
            ("mixed use", "Mixed Use"),
            ("development", "Development"),
        ]
        for key, value in mapping:
            if key in t:
                return value
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
