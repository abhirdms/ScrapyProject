import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class FairhurstBuckleyScraper:
    BASE_URL = "https://fairhurstbuckley.co.uk/sales-lettings/property-search-map/"
    DOMAIN = "https://fairhurstbuckley.co.uk"

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
            "//div[@id='properties']//div[contains(@class,'property')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            "//div[@id='properties']//a[contains(@class,'property-card') "
            "and not(starts-with(@href,'javascript'))]/@href"
        )

        for url in listing_urls:
            url = urljoin(self.DOMAIN, url)

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
            "//h2[contains(@class,'property-title')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS (FIXED) ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//h2[contains(@class,'property-title')]//text()")
        ))

        # ---------- SALE TYPE (IMPROVED LOGIC) ---------- #
        agreement_text = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'agreement')]//text()")
        ))

        sale_type = self.normalize_sale_type(
            agreement_text + " " + display_address + " " +
            self._clean(tree.xpath("string(//body)"))
        )

        if sale_type == "Sold":
            return None  

        # ---------- PROPERTY SUB TYPE (FIXED) ---------- #
        property_sub_type = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'property-meta')]//li/text()")
        ))

        # ---------- DESCRIPTION ---------- #
        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'property-description')]//text() | "
                "//div[contains(@class,'desc')]//text()"
            )
        ))

        # ---------- SIZE ---------- #
        measurement_text = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'measurements')]//text()")
        ))

        size_ft, size_ac = self.extract_size(
            measurement_text + " " + detailed_description
        )

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- PRICE ---------- #
        price_text = self._clean(" ".join(
            tree.xpath("//p[contains(@class,'price')]//text()")
        ))
        price = self.extract_numeric_price(price_text, sale_type)

        # ---------- IMAGES ---------- #
        property_images = list(set([
            src for src in tree.xpath(
                "//div[contains(@class,'property-gallery')]//img/@src"
            ) if src
        ]))

        # ---------- BROCHURE ---------- #
        brochure_urls = list(set([
            href for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
        ]))

        # ---------- AGENT DETAILS ---------- #
        # ---------- AGENT DETAILS (SINGLE CLEAN VALUE) ---------- #

        body_text = tree.xpath("string(//body)")
        body_text = self._clean(body_text)

        # -------- EMAIL (unique + first only) -------- #
        emails = sorted(set(re.findall(
            r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',
            body_text
        )))

        agent_email = emails[0] if emails else ""

        # -------- PHONE (unique + first only) -------- #
        phones = sorted(set(re.findall(
            r'\b0\d{3}\s?\d{3}\s?\d{4}\b',
            body_text
        )))

        agent_phone = phones[0] if phones else ""

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
            "agentCompanyName": "Fairhurst Buckley",
            "agentName": "",
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

        # ===================== SQUARE FEET ===================== #
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*feet)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        # ===================== SQUARE METRES ===================== #
        if not size_ft:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(sqm|sq\.?\s*m|m2|square\s*metres|square\s*meters)',
                text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm_value = min(a, b) if b else a
                size_ft = round(sqm_value * 10.7639, 3)  # convert sqm → sqft

        # ===================== ACRES ===================== #
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac\.?)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        # ===================== HECTARES ===================== #
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
                size_ac = round(hectare_value * 2.47105, 3)  # convert ha → acres

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

    def extract_tenure(self, text):
        if not text:
            return ""
        t = text.lower()
        if "freehold" in t:
            return "Freehold"
        if "leasehold" in t:
            return "Leasehold"
        return ""

    def extract_postcode(self, text: str):
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
        if 'sold' in t or 'sale agreed' in t or 'let agreed' in t:
            return "Sold"
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""