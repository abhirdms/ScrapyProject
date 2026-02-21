import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class RAREScraper:
    BASE_URL = "https://rarecommercialproperty.co.uk/find-a-property/properties"
    DOMAIN = "https://rarecommercialproperty.co.uk"

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
            page_url = f"{self.BASE_URL}?page={page}"

            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'propItemWrap')]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            listing_urls = tree.xpath(
                "//div[contains(@class,'propItemWrap')]"
                "//a[contains(@class,'propImg')]/@href"
            )

            if not listing_urls:
                break

            new_count = 0

            for url in listing_urls:
                if url in self.seen_urls:
                    continue

                self.seen_urls.add(url)
                new_count += 1

                try:
                    obj = self.parse_listing(url)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

            if new_count == 0:
                break

            page += 1

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'property-title')]//h1"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- ADDRESS ---------- #
        title = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'property-title')]//h1/text()")
        ))

        address = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'property-title')]//h2/text()")
        ))

        display_address = self._clean(f"{title}, {address}")

        # ---------- PROPERTY TYPE ---------- #
        property_sub_type = self._clean(" ".join(
            tree.xpath(
                "//table[contains(@class,'property-details__table')]"
                "//tr[td[1][contains(text(),'Property Type')]]/td[2]/text()"
            )
        ))

        # ---------- TENURE ---------- #
        tenure_text = self._clean(" ".join(
            tree.xpath(
                "//table[contains(@class,'property-details__table')]"
                "//tr[td[1][contains(text(),'Tenure')]]/td[2]/text()"
            )
        ))

        sale_type = self.normalize_sale_type(tenure_text)

        # ---------- SIZE ---------- #
        size_text = self._clean(" ".join(
            tree.xpath(
                "//table[contains(@class,'property-details__table')]"
                "//tr[td[1][contains(text(),'Size')]]/td[2]/text()"
            )
        ))

        size_ft, size_ac = self.extract_size(size_text)

        # ---------- DESCRIPTION ---------- #
        summary = self._clean(" ".join(
            tree.xpath("//h2[contains(@class,'property-details__summary')]/text()")
        ))

        hidden_content = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'property-details__hidden-content')]"
                "//*[not(ancestor::div[contains(@class,'relatedLinks')])]/text()"
            )
        ))

        detailed_description = self.clean_description(f"{summary} {hidden_content}")
        tenure = self.extract_tenure(f"{tenure_text} {detailed_description}")

        # ---------- PRICE ---------- #
        price_text = self._clean(" ".join(
            tree.xpath(
                "//table[contains(@class,'property-details__table')]"
                "//tr[td[1][contains(text(),'Rent')]]/td[2]/text()"
            )
        ))

        price = self.extract_numeric_price(price_text, sale_type)

        # ---------- IMAGES (DEDUP SLICK) ---------- #
        property_images = list(set(
            tree.xpath(
                "//div[contains(@class,'slick-slide') "
                "and not(contains(@class,'slick-cloned'))]//img/@src"
            )
        ))

        # ---------- BROCHURE ---------- #
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
            "agentCompanyName": "RARE",
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

        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf)',
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
            "per annum", "pa", "per year", "pcm",
            "per month", "pw", "per week", "rent"
        ]):
            return ""

        m = re.search(r'[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?', t)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))
        if "m" in m.group(0):
            num *= 1_000_000

        return str(int(num))

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

    def clean_description(self, text):
        if not text:
            return ""

        cleaned = re.split(r"\brelated links?\b", text, flags=re.IGNORECASE)[0]
        cleaned = re.split(r"\bvisit marketing website\b", cleaned, flags=re.IGNORECASE)[0]
        return self._clean(cleaned)

    def normalize_sale_type(self, text):
        t = text.lower()
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
