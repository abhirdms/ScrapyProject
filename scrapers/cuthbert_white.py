import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class CuthbertWhiteScraper:
    BASE_URL = "https://cuthbertwhite.com/properties"
    DOMAIN = "https://cuthbertwhite.com"

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
            "//article[contains(@class,'portfolio-item')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            "//article[contains(@class,'portfolio-item')]//h3/a/@href"
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
            "//div[@class='page-title-text']/h1"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//div[@class='page-title-text']/h1/text()")
        ))

        # ---------- SALE TYPE ---------- #
        sale_type_raw = self._clean(" ".join(
            tree.xpath("//div[@class='page-title-text']/following::span[1]/text()")
        ))

        page_text = self._clean(" ".join(tree.xpath("//body//text()")))
        sale_type = self.normalize_sale_type(sale_type_raw) or self.normalize_sale_type(page_text)

        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(page_text, sale_type)
        if not price:
            price_text = self._clean(" ".join(
                tree.xpath("//li/strong[contains(text(),'Offers')]/text()")
            ))
            price = self.extract_numeric_price(price_text, "For Sale")

        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type = ""

        # ---------- DESCRIPTION ---------- #
        description_parts = tree.xpath(
            "//div[contains(@class,'ccm-custom-style-container')]"
            "//p[not(contains(.,'Available Accommodation'))]//text()"
        )
        detailed_description = self._clean(" ".join(description_parts))

        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        size_rows = [
            self._clean(v) for v in tree.xpath("//tbody/tr[position()>1]/td[2]/text()") if self._clean(v)
        ]
        for size_value in size_rows:
            row_ft, row_ac = self.extract_size(size_value)
            if row_ft and (not size_ft or row_ft < size_ft):
                size_ft = row_ft
            if row_ac and (not size_ac or row_ac < size_ac):
                size_ac = row_ac

        if not size_ft:
            size_li = self._clean(" ".join(tree.xpath("//li[contains(text(),'sq ft')]/text()")))
            li_ft, li_ac = self.extract_size(size_li)
            size_ft = li_ft
            size_ac = li_ac or size_ac

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- IMAGES ---------- #
        images = tree.xpath(
            "//div[contains(@class,'flexslider')]"
            "//div[contains(@class,'slide') and not(contains(@class,'clone'))]"
            "//img/@src"
        )
        property_images = list({urljoin(self.DOMAIN, img) for img in images if img})

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'download_file')]/@href")
        ]

        # ---------- AGENT DETAILS ---------- #
        agent_name = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'call-agent')]/h5/text()")
        ))

        agent_email = tree.xpath("//a[starts-with(@href,'mailto:')]/@href")
        agent_email = agent_email[0].replace("mailto:", "") if agent_email else ""

        agent_phone = tree.xpath(
            "//div[contains(@class,'call-agent')]//a[starts-with(@href,'tel:')]/@href"
        )
        agent_phone = agent_phone[0].replace("tel:", "") if agent_phone else ""

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
            "agentCompanyName": "CuthbertWhite",
            "agentName": agent_name,
            "agentCity": "",
            "agentEmail": agent_email,
            "agentPhone": agent_phone,
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }

        print("*****" * 10)
        print(obj)
        print("*****" * 10)

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

        if any(k in t for k in [
            "poa", "price on application", "upon application", "on application"
        ]):
            return ""

        if any(k in t for k in [
            "per annum", "pa", "per year", "pcm",
            "per month", "pw", "per week", "rent"
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
        if "for sale" in t and "to let" in t:
            return "For Sale / To Let"
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
