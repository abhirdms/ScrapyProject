import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class CortexPartnersScraper:
    BASE_URL = "https://www.cortexpartners.co.uk/sales"
    DOMAIN = "https://www.cortexpartners.co.uk"

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
            "//ul[contains(@class,'c-list-sales')]//li[contains(@class,'grid__item')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listings = tree.xpath(
            "//ul[contains(@class,'c-list-sales')]"
            "//li[contains(@class,'grid__item')]"
        )

        for item in listings:

            url = item.xpath(".//a/@href")
            if not url:
                continue

            url = urljoin(self.DOMAIN, url[0])

            if url in self.seen_urls:
                continue
            self.seen_urls.add(url)

            obj = self.parse_listing(item, url)
            if obj:
                self.results.append(obj)

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, item, url):

        # ---------- TITLE ---------- #
        title = self._clean(" ".join(
            item.xpath(".//h3[@class='h-padbtm-10']/text()")
        ))

        # ---------- TOWN ---------- #
        town = self._clean(" ".join(
            item.xpath(".//div[contains(@class,'c-town')]/text()")
        ))

        display_address = f"{title}, {town}" if town else title

        # ---------- DESCRIPTION ---------- #
        description = self._clean(" ".join(
            item.xpath(".//div[contains(@class,'c-content')]//p[not(button)]/text()")
        ))

        detailed_description = description

        # ---------- IMAGE ---------- #
        image_srcset = item.xpath(".//img/@srcset")
        property_images = []
        if image_srcset:
            img = image_srcset[0].split(" ")[0]
            property_images.append(urljoin(self.DOMAIN, img))

        # ---------- BROCHURE (FROM ONCLICK) ---------- #
        brochure_urls = []
        onclick = item.xpath(".//button[contains(@onclick,'window.open')]/@onclick")
        if onclick:
            match = re.search(r"window\.open\('([^']+)'", onclick[0])
            if match:
                brochure_urls.append(match.group(1))

        # ---------- SALE TYPE ---------- #
        sale_type = "For Sale"

        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(detailed_description, sale_type)

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
            "agentCompanyName": "Cortex Partners",
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

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(sq\.?\s*ft\.?|sqft|sf)',
            text
        )
        if m:
            size_ft = round(float(m.group(1)), 3)

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(acres?|acre|ac\.?)',
            text
        )
        if m:
            size_ac = round(float(m.group(1)), 3)

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

        m = re.search(r'£\s*(\d+(?:,\d{3})*)', text)
        if not m:
            return ""

        return m.group(1).replace(",", "")

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
        match = re.search(full_pattern, text)
        return match.group().strip() if match else ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""