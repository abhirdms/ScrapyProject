import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class HutchinsonMorrisonChildsScraper:

    BASE_URL = "https://www.hmc.london/available-property"
    DOMAIN = "https://www.hmc.london"
    AGENT_COMPANY = "Hutchinson Morrison Childs"

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



    def run(self):

        self.driver.get(self.BASE_URL)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'col-md-4') and contains(@class,'col-lg-4')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_blocks = tree.xpath(
            "//div[contains(@class,'col-md-4') and contains(@class,'col-lg-4')]"
        )

        for block in listing_blocks:

            # SAME PDF XPATH
            pdf_relative = block.xpath(".//a/img/parent::a/@href")
            if not pdf_relative:
                continue

            pdf_url = urljoin(self.DOMAIN, pdf_relative[0].strip())

            if pdf_url in self.seen_urls:
                continue

            self.seen_urls.add(pdf_url)

            try:
                obj = self.parse_listing(block, pdf_url)
                if obj:
                    self.results.append(obj)
            except Exception:
                continue

        self.driver.quit()
        return self.results



    def parse_listing(self, block, pdf_url):

        # ---------- ADDRESS (SAME XPATH) ----------
        display_address = self._clean(" ".join(
            block.xpath(".//p/b//text()")
        ))

        # ---------- SALE TYPE (SAME XPATH) ----------
        raw_status = self._clean("".join(
            block.xpath(".//p[@class='orange']/text()")
        ))

        sale_type = self.extract_sale_type(raw_status)

        # ---------- SIZE (SAME XPATH) ----------
        size_text = self._clean("".join(
            block.xpath(".//p/b/following-sibling::text()[1]")
        ))

        size_ft, size_ac = self.extract_size(size_text)

        # ---------- IMAGE (SAME XPATH) ----------
        image = block.xpath(".//img/@src")
        property_images = [
            urljoin(self.DOMAIN, image[0])
        ] if image else []

        # ---------- POSTCODE ----------
        postcode = self.extract_postcode(display_address)

        # ---------- DESCRIPTION (SAME XPATH) ----------
        description_lines = block.xpath(
            ".//p[b]/text()[normalize-space()]"
        )

        detailed_description = self._clean(" ".join(description_lines))

        # ---------- TENURE FROM DESCRIPTION ----------
        tenure = self.extract_tenure(detailed_description)

        obj = {
            "listingUrl": pdf_url,          # SAME AS PDF
            "displayAddress": display_address,
            "price": "",
            "propertySubType": "",
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": postcode,
            "brochureUrl": [pdf_url],
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


    def extract_tenure(self, text):
        if not text:
            return ""

        t = text.lower()

        if "freehold" in t:
            return "Freehold"

        if "leasehold" in t:
            return "Leasehold"

        return ""

    def extract_sale_type(self, text):
        if not text:
            return ""

        t = text.lower()

        if "sale" in t:
            return "For Sale"

        if "let" in t or "to let" in t:
            return "To Let"

        return ""

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower()
        text = text.replace(",", "")
        text = text.replace("ft²", "ft")
        text = text.replace("sq. ft", "sq ft")

        size_ft = ""
        size_ac = ""

        ft_matches = re.findall(
            r'(\d+(?:\.\d+)?)\s*(?:sq\s*ft|sqft|ft)',
            text
        )
        if ft_matches:
            numbers = [float(n) for n in ft_matches]
            size_ft = min(numbers)

        acre_matches = re.findall(
            r'(\d+(?:\.\d+)?)\s*(?:acres?|acre)',
            text
        )
        if acre_matches:
            numbers = [float(n) for n in acre_matches]
            size_ac = min(numbers)

        hectare_matches = re.findall(
            r'(\d+(?:\.\d+)?)\s*(?:hectares?|ha)',
            text
        )
        if hectare_matches:
            numbers = [float(n) * 2.47105 for n in hectare_matches]
            size_ac = min(numbers)

        return size_ft, size_ac

    def extract_postcode(self, text):
        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        t = text.upper()
        m = re.search(FULL, t) or re.search(PARTIAL, t)
        return m.group() if m else ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
