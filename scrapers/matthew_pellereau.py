import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class MatthewPellereauScraper:
    BASE_URL = "https://www.matthewpellereau.co.uk/#portfolio"
    DOMAIN = "https://www.matthewpellereau.co.uk"

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
            "//div[contains(@class,'portfolio-item')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # Build a mapping: portfolio-item element -> its section heading (h2 text)
        # Strategy: walk all elements in document order, track the last h2 seen,
        # and record it for every portfolio-item we encounter.
        subtype_map = self._build_subtype_map(tree)

        listing_blocks = tree.xpath("//div[contains(@class,'portfolio-item')]")

        for block in listing_blocks:
            # Use the pre-built map to get the correct section heading
            property_sub_type = subtype_map.get(id(block), "")
            obj = self.parse_listing(block, property_sub_type)
            if obj:
                self.results.append(obj)

        self.driver.quit()
        return self.results

    # ===================== SUBTYPE MAP ===================== #

    def _build_subtype_map(self, tree):
        """
        Walk the entire document tree in document order.
        Whenever an <h2> is encountered, update the current section label.
        Whenever a div.portfolio-item is encountered, map its id() to the
        current section label.

        This is robust against any nesting depth and avoids broken XPath
        preceding:: axis lookups.
        """
        subtype_map = {}
        current_section = ""

        for element in tree.iter():
            tag = element.tag if isinstance(element.tag, str) else ""

            # Detect section headings
            if tag.lower() == "h2":
                text = self._clean("".join(element.itertext()))
                if text:
                    current_section = text

            # Detect portfolio items
            elif tag.lower() == "div":
                classes = element.get("class", "")
                if "portfolio-item" in classes:
                    subtype_map[id(element)] = current_section

        return subtype_map

    # ===================== LISTING ===================== #

    def parse_listing(self, block, property_sub_type):
        href = self._clean("".join(block.xpath(".//a/@href")))
        if not href:
            return None

        listing_url = urljoin(self.DOMAIN, href)

        if listing_url in self.seen_urls:
            return None
        self.seen_urls.add(listing_url)

        raw_lines = [
            self._clean(x)
            for x in block.xpath(".//a/p//text()")
        ]
        lines = [x for x in raw_lines if x]

        if not lines:
            return None

        display_address = lines[0]
        detailed_description = self._clean(" ".join(lines))

        sale_type = self.normalize_sale_type(detailed_description)
        tenure = self.extract_tenure(detailed_description)
        size_ft, size_ac = self.extract_size(detailed_description)
        price = self.extract_numeric_price(detailed_description, sale_type)

        image_src = self._clean("".join(block.xpath(".//img/@src")))
        property_images = [urljoin(self.DOMAIN, image_src)] if image_src else []

        brochure_url = [listing_url] if listing_url.lower().endswith(".pdf") else []

        obj = {
            "listingUrl": listing_url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_url,
            "agentCompanyName": "Matthew Pellereau",
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
        text = text.replace("m²", "sqm")
        text = text.replace("ft²", "sq ft")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\.?\s*ft\.?|sqft|sf|square\s*feet|sq\s*ft)",
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        if not size_ft:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sqm|m2|sq\.?\s*m)",
                text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm = min(a, b) if b else a
                size_ft = round(sqm * 10.7639, 3)

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac\.?)",
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
            "per annum", "pa", "per year", "pcm", "per month", "pw", "per week", "rent"
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
        if "let" in t or "rent" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""