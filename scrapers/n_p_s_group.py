import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class NPSGroupScraper:
    BASE_URL = "https://property.nps.co.uk/SearchProperties"
    DOMAIN = "https://property.nps.co.uk"

    def __init__(self):
        self.results = []
        self.seen_urls = set()
        self.seen_pages = set()

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
        pending_pages = [self.BASE_URL]

        while pending_pages:
            page_url = pending_pages.pop(0)

            normalized_page = self.normalize_page_url(page_url)
            if normalized_page in self.seen_pages:
                continue
            self.seen_pages.add(normalized_page)

            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//a[contains(@id,'hypDetails') and contains(@href,'propertyInfo')]"
                )))
            except Exception:
                continue

            tree = html.fromstring(self.driver.page_source)

            listing_urls = [
                urljoin(self.DOMAIN, href)
                for href in tree.xpath(
                    "//a[contains(@id,'hypDetails') and contains(@href,'propertyInfo')]/@href"
                )
            ]

            if not listing_urls:
                continue

            for url in listing_urls:
                if url in self.seen_urls:
                    continue

                self.seen_urls.add(url)

                try:
                    obj = self.parse_listing(url)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

            for next_page in self.extract_pagination_urls(tree):
                normalized_next = self.normalize_page_url(next_page)
                if normalized_next not in self.seen_pages:
                    pending_pages.append(next_page)

        self.driver.quit()
        return self.results

    # ===================== DETAIL PAGE ===================== #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h2[contains(@class,'propTitle')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # Header block includes address, sale/price line, subtype, and size.
        header_values = [
            self._clean(" ".join(node.xpath(".//text()")))
            for node in tree.xpath(
                "(//div[contains(@class,'obj100L') and contains(@class,'objMarginBtmLg')])[1]"
                "//h2[contains(@class,'propTitle')]"
            )
        ]
        header_values = [val for val in header_values if val]

        display_address = header_values[0] if len(header_values) > 0 else ""
        sale_price_text = header_values[1] if len(header_values) > 1 else ""
        property_sub_type = header_values[2] if len(header_values) > 2 else ""
        size_text = header_values[3] if len(header_values) > 3 else ""

        sale_type = self.normalize_sale_type(sale_price_text)
        price = self.extract_numeric_price(sale_price_text, sale_type)
        size_ft, size_ac = self.extract_size(size_text)

        bullet_points = [
            self._clean(" ".join(li.xpath(".//text()")))
            for li in tree.xpath("//div[contains(@id,'divBullets')]//li")
        ]
        bullet_points = [point for point in bullet_points if point]

        detailed_description = self._clean(" ".join(bullet_points))

        property_images = []
        for src in tree.xpath("//img[contains(@id,'slideImage_')]/@src"):
            full_src = urljoin(self.DOMAIN, src)
            if full_src not in property_images:
                property_images.append(full_src)

        brochure_urls = []
        for href in tree.xpath("//a[contains(@id,'hypBrochure')]/@href"):
            full_href = urljoin(self.DOMAIN, href)
            if full_href not in brochure_urls:
                brochure_urls.append(full_href)

        agent_name = self._clean(" ".join(
            tree.xpath("(//div[contains(@class,'contactPanel')]//h2[contains(@class,'truncate')])[1]//text()")
        ))
        agent_email = self._clean(" ".join(
            tree.xpath("(//div[contains(@class,'contactPanel')]//a[contains(@href,'mailto:')])[1]//text()")
        ))
        agent_phone = self._clean(" ".join(
            tree.xpath("(//div[contains(@class,'contactPanel')]//h3[contains(@class,'propTitle')])[1]/text()")
        ))

        tenure = self.extract_tenure(" ".join([sale_price_text, detailed_description]))

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
            "agentCompanyName": "NPS Group",
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

    def extract_pagination_urls(self, tree):
        urls = []

        # Search pages include "SearchProperties", while detail pages include "propertyInfo".
        for href in tree.xpath("//a[contains(@href,'SearchProperties')]/@href"):
            full = urljoin(self.DOMAIN, href)
            if "propertyInfo" in full:
                continue
            normalized = self.normalize_page_url(full)
            if normalized not in urls:
                urls.append(normalized)

        return urls

    def normalize_page_url(self, url):
        return url.split("#")[0].rstrip("/")

    def extract_size(self, text):
        if not text:
            return "", ""

        value = text.lower().replace(",", "")
        value = value.replace("sq. ft", "sq ft")
        value = re.sub(r"[–—−]", "-", value)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:sq\s*ft|sqft|square\s*feet|square\s*foot)",
            value
        )
        if m:
            size_ft = round(float(m.group(1)), 3)

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:sq\s*m|sqm|square\s*metres|square\s*meters)",
            value
        )
        if m and not size_ft:
            size_ft = round(float(m.group(1)) * 10.7639, 3)

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:acres?|acre|ac\.?)",
            value
        )
        if m:
            size_ac = round(float(m.group(1)), 3)

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:hectares?|hectare|ha)",
            value
        )
        if m and not size_ac:
            size_ac = round(float(m.group(1)) * 2.47105, 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale":
            return ""

        if not text:
            return ""

        t = text.lower()
        if any(k in t for k in ["poa", "price on application", "upon application"]):
            return ""

        m = re.search(r"[£]\s*(\d+(?:,\d{3})*(?:\.\d+)?)", text)
        if not m:
            return ""

        return str(int(float(m.group(1).replace(",", ""))))

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
        if "let" in t or "rent" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
