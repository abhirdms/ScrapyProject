import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class LexiconCREScraper:
    BASE_URL = "https://lexiconcre.co.uk/properties-available/"
    DOMAIN = "https://lexiconcre.co.uk"

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
            "//div[contains(@class,'flex_column') and contains(@class,'av_one_third')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listings = tree.xpath(
            "//div[contains(@class,'flex_column') and contains(@class,'av_one_third')]"
        )

        for item in listings:

            # ---------- BROCHURE / LISTING URL ---------- #
            brochure = item.xpath(".//a[contains(@href,'.pdf')]/@href")
            if not brochure:
                continue

            pdf_url = urljoin(self.DOMAIN, brochure[0])

            if pdf_url in self.seen_urls:
                continue
            self.seen_urls.add(pdf_url)

            # ---------- DISPLAY ADDRESS ---------- #
            display_address = self._clean(" ".join(
                item.xpath(
                    ".//section[contains(@class,'av_textblock_section')]//p[1]//text()"
                )
            ))

            # ---------- PROPERTY SUB TYPE ---------- #
            property_sub_type = self._clean(" ".join(
                item.xpath(
                    ".//h2[contains(@class,'av-special-heading-tag')]//text()"
                )
            ))

            # ---------- IMAGE ---------- #
            property_image = item.xpath(
                ".//div[contains(@class,'avia-image-container')]//img/@src"
            )
            property_image = property_image[0] if property_image else ""

            # ---------- SIZE (sqft only) ---------- #
            size_text = self._clean(" ".join(
                item.xpath(
                    ".//section[contains(@class,'av_textblock_section')]"
                    "//p[contains(.,'sqft')]//text()"
                )
            ))

            size_ft = self.extract_size(size_text)

            # ---------- SALE TYPE ---------- #
            sale_type = ""
            if "TO LET" in property_sub_type.upper():
                sale_type = "To Let"

            obj = {
                "listingUrl": pdf_url,
                "displayAddress": display_address,
                "price": "",
                "propertySubType": property_sub_type,
                "propertyImage": property_image,
                "detailedDescription": "",
                "sizeFt": size_ft,
                "sizeAc": "",
                "postalCode": self.extract_postcode(display_address),
                "brochureUrl": [pdf_url],
                "agentCompanyName": "Lexicon CRE",
                "agentName": "",
                "agentCity": "",
                "agentEmail": "",
                "agentPhone": "",
                "agentStreet": "",
                "agentPostcode": "",
                "tenure": "",
                "saleType": sale_type,
            }

            self.results.append(obj)

        self.driver.quit()
        return self.results

    # ===================== HELPERS ===================== #

    def extract_size(self, text):
        if not text:
            return ""

        text = text.lower().replace(",", "")
        match = re.search(r'(\d+(?:\.\d+)?)\s*(sq\s*ft|sqft)', text)
        return match.group(1) if match else ""

    def extract_postcode(self, text):
        if not text:
            return ""

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        t = text.upper()
        m = re.search(FULL, t) or re.search(PARTIAL, t)
        return m.group() if m else ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
