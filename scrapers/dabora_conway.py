import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class DaboraConwayScraper:
    BASE_URLS = [
        ("https://www.daboraconway.com/buy/", "For Sale"),
        ("https://www.daboraconway.com/rent/", "To Let"),
    ]
    DOMAIN = "https://www.daboraconway.com"

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
        for base_url, sale_type in self.BASE_URLS:
            self.driver.get(base_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[@id='recent-properties']//div[contains(@class,'property')]"
                )))
            except Exception:
                continue

            tree = html.fromstring(self.driver.page_source)

            listing_urls = tree.xpath(
                "//div[@id='recent-properties']"
                "//div[contains(@class,'property')]"
                "//h4/a[1]/@href"
            )

            for href in listing_urls:
                url = urljoin(self.DOMAIN, href)

                if url in self.seen_urls:
                    continue
                self.seen_urls.add(url)

                try:
                    obj = self.parse_listing(url, sale_type)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url, sale_type):

        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h1"
        )))

        tree = html.fromstring(self.driver.page_source)



        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type_raw = self._clean(" ".join(
            tree.xpath("//p[contains(@class,'type')]/text()")
        ))
        property_sub_type = self.clean_property_sub_type(property_sub_type_raw)

        # ---------- DESCRIPTION ---------- #
        detailed_description = self._clean(" ".join(
            tree.xpath("//div[@id='overview']//text()")
        )) or self._clean(" ".join(
            tree.xpath("//p[contains(@class,'hidden-xs')]/text()")
        ))

        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- PRICE ---------- #
        raw_price = self._clean(" ".join(tree.xpath("//h1/text()")))
        price = self.extract_numeric_price(raw_price, sale_type)

        # ---------- IMAGES ---------- #
        property_images = list(dict.fromkeys([
            urljoin(self.DOMAIN, src)
            for src in tree.xpath(
                "//div[@id='property-carousel']//img/@src"
            )
            if src
        ]))

        # ---------- BROCHURE ---------- #
        brochure_urls = list(dict.fromkeys([
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
        ]))

        agent_phone = self.extract_agent_phone(" ".join(
            tree.xpath(
                "//div[contains(@class,'property-contact')]"
                "//a[starts-with(@href,'tel:')]/text()"
            )
        ))

        obj = {
            "listingUrl": url,
            "displayAddress": "",
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(detailed_description),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Dabora Conway",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": agent_phone,
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }

        return obj

    # ===================== HELPERS ===================== #

    def extract_numeric_price(self, text, sale_type):
        if not text:
            return ""

        t = text.lower()

        if any(k in t for k in [
            "poa", "price on application", "upon application", "on application"
        ]):
            return ""

        m = re.search(r"[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?", t)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))
        if "m" in m.group(0):
            num *= 1_000_000

        if sale_type == "For Sale":
            return str(int(num))

        if sale_type == "To Let":
            return str(int(num))

        return str(int(num))

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
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        if not size_ft:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
                r"(sqm|sq\.?\s*m|m2|square\s*metres|square\s*meters)",
                text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm_value = min(a, b) if b else a
                size_ft = round(sqm_value * 10.7639, 3)

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(acres?|acre|ac\.?)",
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        if not size_ac:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
                r"(hectares?|ha)",
                text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                hectare_value = min(a, b) if b else a
                size_ac = round(hectare_value * 2.47105, 3)

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

    def extract_agent_phone(self, text):
        if not text:
            return ""

        m = re.search(r"(\+?\d[\d\s\-\(\)]{7,}\d)", text)
        return self._clean(m.group(1)) if m else ""

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
        if "rent" in t or "to let" in t or "lettings" in t:
            return "To Let"
        return ""

    def clean_property_sub_type(self, text):
        if not text:
            return ""

        cleaned = re.sub(r"\b\d+\s*bed\b", "", text, flags=re.I)
        cleaned = re.sub(
            r"\b(for sale|to let|under offer|sstc|let agreed|sold stc)\b",
            "",
            cleaned,
            flags=re.I
        )
        return self._clean(cleaned)

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
