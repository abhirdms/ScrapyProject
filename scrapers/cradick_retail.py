import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class CradickRetailScraper:
    BASE_URL = "https://www.cradick.co.uk/properties/"
    DOMAIN = "https://www.cradick.co.uk"

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
            "//div[contains(@class,'property-card-outer')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            "//div[contains(@class,'property-card-outer')]//a/@href"
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
            "//div[contains(@class,'col-10')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'col-10')]//h1/text() | "
                "//div[contains(@class,'col-10')]//h2/text()"
            )
        ))

        # ---------- PRICE ---------- #
        price_text = self._clean(" ".join(
            tree.xpath("//h4[text()='Rent']/following-sibling::p/text()")
        ))

        # ---------- SALE TYPE ---------- #
        sale_type_raw = self._clean(" ".join(
            tree.xpath("//h4[contains(text(),'Availability')]/following-sibling::p/text()")
        ))

        sale_type = self.normalize_sale_type(sale_type_raw)

        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type = ""

        # ---------- DESCRIPTION ---------- #
        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//h2[text()='Description']/following-sibling::p[1]//text()"
            )
        ))

        # ---------- SIZE ---------- #
        size_text = self._clean(" ".join(
            tree.xpath("//h4[contains(text(),'Area')]/following-sibling::p/text()")
        ))

        size_ft, size_ac = self.extract_size(size_text)

        # ---------- TENURE ---------- #
        tenure = self._clean(" ".join(
            tree.xpath("//h4[contains(text(),'Tenure')]/following-sibling::p/text()")
        ))

        # ---------- IMAGES ---------- #
        property_images = [
            urljoin(self.DOMAIN, src)
            for src in tree.xpath(
                "//div[contains(@class,'carousel-inner')]//img/@src"
            )
        ]

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath(
                "//div[contains(@class,'category')]//a[contains(@href,'.pdf')]/@href"
            )
        ]

        # ---------- AGENT DETAILS ---------- #
        agent_name = ""
        agent_email = ""
        agent_phone = ""

        agent_blocks = tree.xpath("//div[contains(@class,'agent')]")
        if agent_blocks:
            first_agent = agent_blocks[0]

            name_texts = [
                self._clean(t) for t in first_agent.xpath(".//h4/text()") if self._clean(t)
            ]
            if name_texts:
                agent_name = name_texts[0]

            email_hrefs = first_agent.xpath(
                ".//a[starts-with(@href,'mailto:')]/@href"
            )
            if email_hrefs:
                agent_email = email_hrefs[0].replace("mailto:", "").strip()

            phone_texts = first_agent.xpath(
                ".//a[starts-with(@href,'tel:')]/text()"
            )
            if phone_texts:
                agent_phone = self._clean(phone_texts[0])

        # ---------- PRICE NORMALIZATION ---------- #
        price = self.extract_numeric_price(price_text, sale_type)

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
            "agentCompanyName": "Cradick Retail",
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

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\.?\s*ft\.?|sqft|sf)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale":
            return ""

        if not text:
            return ""

        t = text.lower()

        if any(k in t for k in [
            "poa", "price on application", "upon application", "on request"
        ]):
            return ""

        if any(k in t for k in [
            "per annum", "pa", "per year", "pcm", "rent"
        ]):
            return ""

        m = re.search(r'[£]\s*(\d+(?:,\d{3})*)', t)
        if not m:
            return ""

        return m.group(1).replace(",", "")

    def extract_postcode(self, text):
        if not text:
            return ""

        text = text.upper()
        full_pattern = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'

        match = re.search(full_pattern, text)
        return match.group().strip() if match else ""

    def normalize_sale_type(self, text):
        t = text.lower()
        if "sale" in t:
            return "For Sale"
        if "let" in t:
            return "To Let"
        if "offer" in t:
            return "For Sale"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
