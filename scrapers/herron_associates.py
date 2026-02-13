import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html

class HerronAssociatesScraper:

    BASE_URL = "http://herronassociates.co.uk/available-properties.html"
    DOMAIN = "http://herronassociates.co.uk"
    AGENT_COMPANY = "Herron Associates"

    def __init__(self):

        self.results = []
        self.seen_urls = set()

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")

        service = Service("/usr/bin/chromedriver")
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 20)

    # ============================================================
    # RUN
    # ============================================================

    def run(self):

        self.driver.get(self.BASE_URL)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'catItemView')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_blocks = tree.xpath("//div[contains(@class,'catItemView')]")

        for block in listing_blocks:

            relative = block.xpath(".//h3[@class='catItemTitle']/a/@href")
            if not relative:
                continue

            url = urljoin(self.DOMAIN, relative[0])

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

    # ============================================================
    # LISTING PAGE
    # ============================================================

    def parse_listing(self, url):

        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h2[@class='itemTitle']"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- ADDRESS ----------
        display_address = self._clean(" ".join(
            tree.xpath("//h2[@class='itemTitle']/text()")
        ))

                # Remove script/style
        for bad in tree.xpath("//script|//style"):
            bad.getparent().remove(bad)

        # Remove HTML comments (this removes the var prefix block)
        for comment in tree.xpath("//comment()"):
            parent = comment.getparent()
            if parent is not None:
                parent.remove(comment)

        # Extract clean text
        detailed_description = self._clean(
            tree.xpath("string(//div[@class='itemFullText'])")
        )

        desc_lower = detailed_description.lower()

        # ---------- SALE TYPE ----------
        sale_type = ""
        if "to let" in desc_lower:
            sale_type = "To Let"
        elif "for sale" in desc_lower or "sale of the property" in desc_lower:
            sale_type = "For Sale"

        # ---------- PRICE ----------
        price_raw = self._clean(" ".join(
            tree.xpath("//div[@class='itemExtraFields']//li[contains(text(),'£')]/text()")
        ))

        price = self.normalize_price(price_raw, sale_type)

        # ---------- SIZE (FROM DESCRIPTION) ----------
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- IMAGES (USE XL VERSION) ----------
        property_images = list(set(
            tree.xpath("//div[@class='itemImageBlock']//a/@href")
        ))

        # ---------- BROCHURE ----------
        brochure_urls = list(set(
            urljoin(self.DOMAIN, b)
            for b in tree.xpath("//a[contains(text(),'Download')]/@href")
            if b
        ))

        # ---------- TENURE ----------
        tenure = self.extract_tenure(detailed_description)

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": "",
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

    # ============================================================
    # HELPERS
    # ============================================================

    def normalize_price(self, price_text, sale_type):

        if sale_type != "For Sale":
            return ""

        if not price_text:
            return ""

        if "poa" in price_text.lower():
            return ""

        m = re.search(r'£\s?([\d,]+)', price_text)
        if not m:
            return ""

        return m.group(1).replace(",", "")

    def extract_size(self, text):

        if not text:
            return "", ""

        text = text.lower()
        text = text.replace("\xa0", " ")
        text = text.replace(",", "")
        text = text.replace("ft²", "ft")
        text = text.replace("m²", "m2")

        size_ft = ""
        size_ac = ""

        # ---- SQ FT ----
        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:sq\s*ft|sqft|ft)', text)
        if m:
            size_ft = float(m.group(1))

        # ---- ACRES ----
        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:acres?|acre)', text)
        if m:
            size_ac = float(m.group(1))

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

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
