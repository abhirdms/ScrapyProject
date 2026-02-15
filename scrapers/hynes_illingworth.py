import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class HynesIllingworthScraperAbhi:
    BASE_URL = "https://www.hynesillingworth.co.uk/properties/"
    DOMAIN = "https://www.hynesillingworth.co.uk"

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
            "//div[contains(@class,'property-card')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            "//div[contains(@class,'property-card')]"
            "//a[contains(@class,'property-overlay')]/@href"
        )

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

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'header-grid-2-col')]//h1"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'header-grid-2-col')]//h1/text()"
            )
        ))

        # ---------- PROPERTY IMAGE ---------- #
        image_styles = tree.xpath(
            "//div[contains(@class,'property-card-img')]/@style"
        )

        property_images = []
        for style in image_styles:
            m = re.search(r'url\("(.*?)"\)', style)
            if m:
                property_images.append(m.group(1))

        # ---------- DESCRIPTION ---------- #
        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'property-details-wrapper')]"
                "//text()[normalize-space()]"
            )
        ))

        # ---------- SIZE ---------- #
        size_ft = ""
        size_ac = ""

        strong_sizes = tree.xpath(
            "//h4[normalize-space()='Accomodation']"
            "/following-sibling::div//strong/text()"
        )

        para_sizes = tree.xpath(
            "//h4[normalize-space()='Accomodation']"
            "/following-sibling::div//p[contains(.,'sq ft')]/text()"
        )

        size_text = " ".join(strong_sizes + para_sizes)
        size_ft, size_ac = self.extract_size(size_text)

        # ---------- TENURE ---------- #
        tenure = self._clean(" ".join(
            tree.xpath(
                "//h4[normalize-space()='Lease']"
                "/following-sibling::p/text()"
            )
        )) or self.extract_tenure(detailed_description)

        # ---------- PRICE ---------- #
        price_text = self._clean(" ".join(
            tree.xpath(
                "//div[h4[normalize-space()='Rent & Review']]//p/text()"
            )
        ))

        sale_type = self.normalize_sale_type(
            " ".join(
                tree.xpath(
                    "//img[contains(@class,'location-map')]/@src"
                )
            )
        )

        price = self.extract_numeric_price(price_text or detailed_description, sale_type)

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@class,'download')]/@href")
        ]

        # ---------- AGENT DETAILS ---------- #
        viewing_text = " ".join(
            tree.xpath(
                "//h4[normalize-space()='Viewing']"
                "/following-sibling::div//text()[normalize-space()]"
            )
        )

        agent_name = ""
        agent_email = ""
        agent_phone = ""

        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', viewing_text)
        if email_match:
            agent_email = email_match.group()

        phone_match = re.search(r'\+?\d[\d\s]{7,}', viewing_text)
        if phone_match:
            agent_phone = phone_match.group().strip()

        agent_name = viewing_text.replace(agent_email, "").replace(agent_phone, "").strip()

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Hynes Illingworth",
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

        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\s*ft|sqft|sf)', text)
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac)', text)
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
            "poa", "price on application", "upon application",
            "on application", "subject to contract"
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

    def normalize_sale_type(self, text):
        t = text.lower()
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
