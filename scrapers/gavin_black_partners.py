import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class GavinBlackPartnersScraper:
    BASE_URL = "https://www.naylorsgavinblack.co.uk/property-search/"
    DOMAIN = "https://www.naylorsgavinblack.co.uk"

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
            "//div[contains(@class,'property-card-wrapper')]"
        )))

        # -------- LOAD MORE LOOP -------- #
        while True:
            try:
                load_more = self.driver.find_element(
                    By.XPATH,
                    "//button[contains(@class,'load-more-button')]"
                )
                self.driver.execute_script("arguments[0].click();", load_more)
                self.wait.until(EC.staleness_of(load_more))
            except Exception:
                break

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            "//a[contains(@class,'featured-property-card')]/@href"
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
            "//h1[contains(@class,'property-address')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//h1[contains(@class,'property-address')]/text()")
        ))

        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'property-item')"
                " and not(contains(.,'Sq Ft'))"
                " and not(contains(.,'Acre'))"
                " and not(contains(.,'Let'))"
                " and not(contains(.,'Sale'))"
                "][1]/text()"
            )
        ))

        # ---------- SALE TYPE ---------- #
        sale_type_raw = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'property-item')"
                " and (contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'sale')"
                " or contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'let'))]"
                "/text()"
            )
        ))
        sale_type = self.normalize_sale_type(sale_type_raw)

        # ---------- SIZE TEXT ---------- #
        size_text = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'property-item')"
                " and (contains(.,'Sq') or contains(.,'Acre') or contains(.,'Hectare'))]"
                "/text()"
            )
        ))

        # ---------- DESCRIPTION ---------- #
        location_text = self._clean(" ".join(
            tree.xpath(
                "//h2[normalize-space()='Location']/following-sibling::p[1]//text()"
            )
        ))

        description_text = self._clean(" ".join(
            tree.xpath(
                "//h2[normalize-space()='Description']/following-sibling::p[1]//text()"
            )
        ))

        detailed_description = " ".join(
            part for part in [location_text, description_text] if part
        )

        # ---------- SIZE EXTRACTION ---------- #
        size_ft, size_ac = self.extract_size(size_text)

        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(size_text, sale_type)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- IMAGES (DEDUPED) ---------- #
        property_images = list(dict.fromkeys(
            tree.xpath(
                "//div[contains(@class,'property-main-images')]"
                "//img[not(contains(@src,'marketstatus'))]/@src"
            )
        ))

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
        ]

        # ---------- FIRST AGENT ONLY ---------- #
        agent_block = tree.xpath("(//div[contains(@class,'agent-item')])[1]")

        agent_name = ""
        agent_email = ""
        agent_phone = ""

        if agent_block:
            agent_tree = agent_block[0]

            agent_name = self._clean(" ".join(
                agent_tree.xpath(".//p[contains(@class,'contact-name')]/text()")
            ))

            email = agent_tree.xpath(".//a[starts-with(@href,'mailto:')]/@href")
            if email:
                agent_email = email[0].replace("mailto:", "").strip()

            phone = agent_tree.xpath(".//a[starts-with(@href,'tel:')]/@href")
            if phone:
                agent_phone = phone[0].replace("tel:", "").strip()

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
            "agentCompanyName": "Naylors Gavin Black",
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
        text = text.replace("ft²", "sq ft")
        text = text.replace("m²", "sqm")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        # SQ FT
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft|sqft|sf)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        # SQM → SQFT
        if not size_ft:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(sqm|m2)',
                text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm_value = min(a, b) if b else a
                size_ft = round(sqm_value * 10.7639, 3)

        # ACRES
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        # HECTARES → ACRES
        if not size_ac:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(hectares?|ha)',
                text
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