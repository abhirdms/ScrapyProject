import re
from urllib.parse import urljoin, unquote

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class DBASdvisorsScraper:
    BASE_URL = "https://www.dbaprop.co.uk/properties/propertiesb0f1.html?pid=774&ss=0"
    DOMAIN = "https://www.dbaprop.co.uk"
    AGENT_COMPANY = "DBA Advisors"

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
            "//div[@class='content_properties']//div[@class='full']"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            "//div[@class='content_properties']//div[@class='full']"
            "//div[@class='column2']//a/@href"
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
            "//div[@class='column1']/h2"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//div[@class='column1']/h2[1]/text()")
        ))

        # ---------- SALE TYPE ---------- #
        sale_type_raw = self._clean(" ".join(
            tree.xpath("//span[@class='status']/text()")
        ))

        sale_type = self.normalize_sale_type(sale_type_raw)
        if sale_type == 'Sold':
            return None

        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type = self._clean(" ".join(
            tree.xpath("//span[@class='area']/text()")
        ))

        # ---------- PRICE ---------- #
        price_raw = self._clean(" ".join(
            tree.xpath("//span[@class='price']/text()")
        ))
        price = self.extract_numeric_price(price_raw)

        # ---------- TENURE ---------- #
        tenure_text = self._clean(" ".join(
            tree.xpath("//p[strong[contains(text(),'Tenure')]]//text()")
        ))
        tenure = self.extract_tenure(tenure_text)

        # ---------- DESCRIPTION ---------- #
        description = self._clean(" ".join(
            tree.xpath(
                "//h2[contains(text(),'Investment summary')]"
                "/following-sibling::p[1]//text()"
            )
        ))

        detailed_description = description

        # ---------- SIZE (FROM DESCRIPTION) ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- IMAGES (FULL SIZE FROM ONCLICK) ---------- #
        property_images = []

        onclick_values = tree.xpath(
            "//div[@class='thumbs']//img/@onclick"
        )

        for val in onclick_values:
            match = re.search(r"src='([^']+)'", val)
            if match:
                img_path = match.group(1)
                full_url = urljoin(self.DOMAIN, img_path)
                property_images.append(full_url)

        # Fallback
        if not property_images:
            thumbs = tree.xpath("//img[@id='display_pic']/@src")
            for t in thumbs:
                property_images.append(urljoin(self.DOMAIN, t))

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
            "agentCompanyName": self.AGENT_COMPANY,
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

        m = re.search(r'(\d+(?:\.\d+)?)\s*sq\s*ft', text)
        if m:
            size_ft = str(int(float(m.group(1))))

        m = re.search(r'(\d+(?:\.\d+)?)\s*acres?', text)
        if m:
            size_ac = str(float(m.group(1)))

        return size_ft, size_ac

    def extract_numeric_price(self, price_raw):
        if not price_raw:
            return ""

        text = price_raw.lower()

        if "poa" in text:
            return ""

        m = re.search(r'(\d+(?:,\d{3})*(?:\.\d+)?)', text)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))

        if "+" in text:
            return str(int(num))

        return str(int(num))

    def extract_tenure(self, text):
        t = text.lower()
        if "freehold" in t:
            return "Freehold"
        if "leasehold" in t:
            return "Leasehold"
        return ""
    
    def normalize_sale_type(self, text):
        if not text:
            return ""

        t = text.lower()

        if "sale" in t:
            return "For Sale"

        if "acquired" in t:
            return "Sold"

        if "sold" in t:
            return "Sold"

        if "rent" in t or "to let" in t:
            return "To Let"

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

    def _clean(self, val):
        return " ".join(val.split()) if val else ""