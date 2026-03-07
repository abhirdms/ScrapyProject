import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class CharterwoodScraper:
    BASE_URL = "http://charterwood.com/?location=Bodmin"
    DOMAIN = "http://charterwood.com"

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

        location_urls = self.get_location_urls()

        for loc_url in location_urls:

            self.driver.get(loc_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//table[@border='1']//tr"
                )))
            except:
                continue

            tree = html.fromstring(self.driver.page_source)

            listing_urls = tree.xpath(
                "//table[@border='1']//tr//a[contains(@class,'boldlink')]/@href"
            )

            for href in listing_urls:
                url = urljoin(self.DOMAIN + "/", href)

                if url in self.seen_urls:
                    continue
                self.seen_urls.add(url)

                try:
                    obj = self.parse_listing(url)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

        self.driver.quit()
        return self.results
    
    def get_location_urls(self):
        self.driver.get(self.DOMAIN)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//a[contains(@href,'?location=')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        hrefs = tree.xpath("//a[contains(@href,'?location=')]/@href")

        urls = []
        for h in hrefs:
            full = urljoin(self.DOMAIN + "/", h)
            if full not in urls:
                urls.append(full)

        return urls

    # ===================== LISTING ===================== #

    def parse_listing(self, url):

        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//font[@size='4']"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- TITLE ---------- #
        title_text = self._clean(" ".join(
            tree.xpath("//font[@size='4']/text()")
        ))
        title_clean = re.sub(r'\s+', ' ', title_text).strip()

        # ---------- SALE TYPE ---------- #
        sale_type = self.normalize_sale_type(title_clean)

        # ---------- SPLIT TITLE INTO TYPE / ADDRESS ---------- #
        parts = re.split(
            r'\bFOR\s+SALE\s+OR\s+TO\s+LET\b|\bFOR\s+SALE\b|\bTO\s+LET\b',
            title_clean,
            flags=re.I
        )

        left = parts[0].strip()
        right = parts[1].strip() if len(parts) > 1 else ""

        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type = re.sub(r'\s*-\s*$', '', left)
        property_sub_type = self._clean(property_sub_type.title())

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = re.sub(r'^\s*-\s*', '', right)
        display_address = self._clean(display_address)

        # ---------- DESCRIPTION (CLEAN) ---------- #
        desc_parts = tree.xpath("//p[@align='left']//text()")

        clean_lines = []
        for t in desc_parts:
            t = self._clean(t)
            if not t:
                continue

            tl = t.lower()
            if "eval(unescape" in tl:
                continue
            if "misdescription act" in tl:
                continue
            if "money laundering regulations" in tl:
                continue
            if "charterwood for themselves" in tl:
                continue

            clean_lines.append(t)

        short_desc = self._clean(" ".join(tree.xpath("//h2/text()")))

        detailed_description = " ".join(
            part for part in [short_desc, " ".join(clean_lines)] if part
        )

        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(detailed_description, sale_type)

        # ---------- PROPERTY REF ID ---------- #
        ref_match = re.search(r'ref=(\w+)', url, re.I)
        ref_id = ref_match.group(1) if ref_match else ""

        # ---------- IMAGES (PROPERTY ONLY) ---------- #
        property_images = []
        for src in tree.xpath("//img[contains(@src,'dbimages')]/@src"):
            if ref_id and f"\\{ref_id}" in src:
                property_images.append(urljoin(self.DOMAIN + "/", src))

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
        ]

        # ---------- AGENT DETAILS (FIRST ONLY) ---------- #
        page_text = self._clean(" ".join(tree.xpath("//body//text()")))

        # PHONE (clean digits only)
        phone_match = re.search(
            r'(\+?44\s?\(?0?\d{2,5}\)?\s?\d{3,4}\s?\d{3,4}|\(?0\d{3,5}\)?\s?\d{3,4}\s?\d{3,4})',
            page_text
        )

        agent_phone = ""
        if phone_match:
            raw_phone = phone_match.group(1)
            agent_phone = re.sub(r"[^\d+]", "", raw_phone)

        # AGENT NAME (first)
        agent_name = ""
        name_match = re.search(
            r'Contact\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',
            page_text
        )
        if name_match:
            agent_name = name_match.group(1)

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
            "agentCompanyName": "Charterwood",
            "agentName": agent_name,
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
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf|square\s*feet|sq\s*feet)',
            text
        )

        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        if not size_ft:

            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(sqm|sq\.?\s*m|m2)',
                text
            )

            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm_value = min(a, b) if b else a
                size_ft = round(sqm_value * 10.7639, 3)

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre)',
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
            "poa", "price on application", "upon application"
        ]):
            return ""

        if any(k in t for k in [
            "per annum", "pa", "rent", "per year"
        ]):
            return ""

        m = re.search(r'[£]\s*(\d+(?:,\d{3})*(?:\.\d+)?)', t)

        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))

        return str(int(num))


    def extract_tenure(self, text):

        if not text:
            return ""

        t = text.lower()

        if "freehold" in t:
            return "Freehold"

        if "lease" in t:
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

        if "let" in t or "rent" in t:
            return "To Let"

        return ""


    def _clean(self, val):
        return " ".join(val.split()) if val else ""