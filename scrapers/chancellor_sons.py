import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class ChancellorSonsScraper:
    BASE_URL = "http://www.homes-on-line.com/cgi-bin/hol/search1.cgi?HEADER=chancellor-sons%2Fheader.htm&INDEX=surrey%2Fchancellor-sons.133%2F__localind&TYPE=FS&AREA=ALL&BED=0&H=true&F=true&FARM=true&MIN=100&MAX=2%2C000%2C000&image=Search+Now&email="
    DOMAIN = "http://www.homes-on-line.com"

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
            "//a[contains(@href,'full_agent')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_urls = list(set(tree.xpath("//a[contains(@href,'full_agent')]/@href")))

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
            "//td[@bgcolor='#E3411F']//b"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- HEADER TEXTS (ADDRESS + PRICE) ---------- #

        header_texts = [
            self._clean(t)
            for t in tree.xpath("//td[@bgcolor='#E3411F']//b/text()")
            if self._clean(t)
        ]

        display_address = header_texts[0] if len(header_texts) > 0 else ""
        price_text = header_texts[1] if len(header_texts) > 1 else ""

        # ---------- SALE TYPE (METHOD-DRIVEN) ---------- #

        sale_type = self.normalize_sale_type(tree.text_content())

        if sale_type == "Sold":
            return None

        # ---------- DESCRIPTION ---------- #

        short_desc = self._clean(" ".join(
            tree.xpath("//span[@class='bodytext']/text()")
        ))

        features = self._clean(" ".join(
            tree.xpath("//p[@align='center']//span[@class='bodytext']//text()")
        ))

        long_desc = self._clean(" ".join(
            tree.xpath("//div[@class='bodytext']//text()")
        ))

        detailed_description = " ".join(
            part for part in [short_desc, features, long_desc] if part
        )

        # ---------- PROPERTY SUB TYPE ---------- #

        property_sub_type = ""

        m = re.search(
            r'(semi[- ]detached|detached|bungalow|flat|apartment|house)',
            detailed_description,
            re.I
        )

        if m:
            property_sub_type = m.group(1).title()

        # ---------- SIZE ---------- #

        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- TENURE ---------- #

        tenure = self.extract_tenure(detailed_description)

        # ---------- PRICE (ONLY FOR SALE) ---------- #

        price = ""
        if sale_type == "For Sale":
            m = re.search(r'[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)', price_text)
            if m:
                price = str(int(float(m.group(1).replace(",", ""))))

        # ---------- IMAGES ---------- #

        property_images = [
            urljoin(self.DOMAIN, src)
            for src in tree.xpath("//img[contains(@src,'/pics/')]/@src")
        ]

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
            "agentCompanyName": "Chancellor & Sons",
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

    def normalize_sale_type(self, text):
        if not text:
            return ""

        t = text.lower()

        if "sold" in t:
            return "Sold"
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""


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
            r'(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*feet)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

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
                size_ft = round(sqm_value * 10.7639, 3)

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac\.?)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

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


    def _clean(self, val):
        return " ".join(val.split()) if val else ""