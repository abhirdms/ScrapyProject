import re
from urllib.parse import parse_qs, urljoin, urlparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from lxml import html


class FifieldGlynScraper:
    BASE_URL = "https://www.fifieldglyn.com/sales-lettings/"
    DOMAIN = "https://www.fifieldglyn.com"

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
                    "//ul[contains(@class,'properties')]/li[contains(@class,'property')]",
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)
            listing_cards = tree.xpath(
                "//ul[contains(@class,'properties')]/li[contains(@class,'property')]"
            )

            if not listing_cards:
                break

            page_new_urls = 0

            for card in listing_cards:
                sale_type_hint = self.get_sale_type_from_listing(card)
                if sale_type_hint == "Sold":
                    continue

                href = self._first_or_empty(card.xpath(".//h3/a/@href"))
                if not href:
                    continue

                url = urljoin(self.DOMAIN, href)
                if url in self.seen_urls:
                    continue

                self.seen_urls.add(url)
                page_new_urls += 1

                try:
                    obj = self.parse_listing(url, sale_type_hint=sale_type_hint)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

            if page_new_urls == 0:
                break

            page += 1

        self.driver.quit()
        return self.results

    # ===================== DETAIL ===================== #

    def parse_listing(self, url, sale_type_hint=""):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h1[contains(@class,'property_title')]",
        )))

        tree = html.fromstring(self.driver.page_source)

        display_address = self._clean(" ".join(
            tree.xpath("//h1[contains(@class,'property_title')]/text()")
        ))

        property_sub_type = self._clean(" ".join(
            tree.xpath("//li[contains(@class,'property-type')]/text()")
        ))

        floor_area_text = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'floor-area')]//text()")
        ))

        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'summary-contents')]//text()[normalize-space()]"
            )
        ))

        sale_price_text = self._clean(" ".join(
            tree.xpath("//span[contains(@class,'commercial-price')]/text()")
        ))
        rent_price_text = self._clean(" ".join(
            tree.xpath("//span[contains(@class,'commercial-rent')]/text()")
        ))
        availability_text = self._clean(" ".join(
            tree.xpath("//li[contains(@class,'availability')]//text()[normalize-space()]")
        ))
        sale_type = sale_type_hint or self.normalize_sale_type(
            " ".join([availability_text, sale_price_text, rent_price_text, detailed_description])
        )

        if sale_type == "Sold":
            return None

        size_ft, size_ac = self.extract_size(" ".join([floor_area_text, detailed_description]))
        tenure = self.extract_tenure(detailed_description)
        price = self.extract_numeric_price(sale_price_text, sale_type)
        if not price and sale_type == "For Sale":
            price = self.extract_numeric_price(detailed_description, sale_type)

        image_urls = []
        for img in tree.xpath("//a[contains(@class,'propertyhive-main-image')]/@href"):
            img = self._clean(img)
            if img and img not in image_urls:
                image_urls.append(img)

        brochure_urls = []
        for href in tree.xpath("//li[contains(@class,'action-brochure')]//a/@href"):
            normalized = self.extract_brochure_url(href)
            if normalized and normalized not in brochure_urls:
                brochure_urls.append(normalized)

        agent_city = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'office-name')]/text()")
        ))
        agent_street = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'office-address')]//text()")
        ))
        agent_phone = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'office-telephone-number')]//a/text()")
        ))

        page_text = self._clean(" ".join(tree.xpath("//text()")))
        agent_email = self.extract_email(page_text)

        inspection_name = self.extract_inspection_name(tree)
        agent_name = inspection_name

        postcode = self.extract_postcode(display_address) or self.extract_postcode(agent_street)

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": image_urls,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": postcode,
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Fifield Glyn",
            "agentName": agent_name,
            "agentCity": agent_city,
            "agentEmail": agent_email,
            "agentPhone": agent_phone,
            "agentStreet": agent_street,
            "agentPostcode": self.extract_postcode(agent_street),
            "tenure": tenure,
            "saleType": sale_type,
        }

        return obj

    # ===================== HELPERS ===================== #

    def get_sale_type_from_listing(self, listing):
        li_class = " ".join(listing.xpath("./@class")).lower()

        if "availability-to-let" in li_class:
            return "To Let"
        if "availability-under-offer" in li_class:
            return "For Sale"
        if "availability-sold" in li_class:
            return "Sold"
        if "availability-available" in li_class:
            return "For Sale"

        return self.normalize_sale_type(li_class)

    def extract_brochure_url(self, href):
        if not href:
            return ""

        full = urljoin(self.DOMAIN, href)
        parsed = urlparse(full)
        query = parse_qs(parsed.query)
        raw_pdf = self._first_or_empty(query.get("href", []))
        return urljoin(self.DOMAIN, raw_pdf) if raw_pdf else full

    def extract_inspection_name(self, tree):
        lines = [
            self._clean(x)
            for x in tree.xpath(
                "//div[contains(@class,'summary-contents')]//text()[normalize-space()]"
            )
            if self._clean(x)
        ]

        for i, text in enumerate(lines):
            if "inspection" in text.lower() and i + 1 < len(lines):
                maybe_name = lines[i + 1]
                if re.search(r"[A-Za-z]", maybe_name):
                    if "@" not in maybe_name and "www." not in maybe_name.lower():
                        return maybe_name
        return ""

    def extract_email(self, text):
        if not text:
            return ""
        m = re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text, re.I)
        return m.group(0) if m else ""

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

        if any(k in t for k in ["poa", "price on application", "upon application", "on application"]):
            return ""

        if any(k in t for k in ["per annum", "pa", "per year", "pcm", "per month", "pw", "per week", "rent"]):
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

        t = text.upper()

        full_pattern = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b"
        partial_pattern = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\b"

        match = re.search(full_pattern, t)
        if match:
            return match.group().strip()

        match = re.search(partial_pattern, t)
        return match.group().strip() if match else ""

    def normalize_sale_type(self, text):
        t = text.lower() if text else ""
        if "sold" in t:
            return "Sold"
        if "sale" in t  or "under offer" in t:
            return "For Sale"
        if "rent" in t or "to let" in t or "let" in t:
            return "To Let"
        return ""

    def _first_or_empty(self, values):
        return values[0].strip() if values else ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
