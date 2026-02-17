import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class LeightonGoldhillScraper:
    BASE_URLS = [
        "https://www.leightongoldhill.com/portfolios/offices/",
        "https://www.leightongoldhill.com/portfolios/industrial-distribution/"
    ]
    DOMAIN = "https://www.leightongoldhill.com"
    AGENT_COMPANY = "Leighton Goldhill"

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

        for base_url in self.BASE_URLS:
            self.driver.get(base_url)

            self.wait.until(EC.presence_of_element_located((
                By.XPATH,
                "//div[contains(@class,'portfolio')]"
            )))

            tree = html.fromstring(self.driver.page_source)

            property_sub_type = self._clean(" ".join(
                tree.xpath("//div[@class='head_text']/h2/text()")
            ))

            listings = tree.xpath(
                "//div[contains(@class,'box') and contains(@class,'portfolio')]"
            )

            for listing in listings:

                href = listing.xpath(".//h5/a/@href")
                if not href:
                    continue

                url = urljoin(self.DOMAIN, href[0].strip())

                if url in self.seen_urls:
                    continue

                # -------- GET STATUS FROM OUTER CARD -------- #
                status_text = self._clean(" ".join(
                    listing.xpath(".//div[@class='portfolio_info']//p/strong[1]/text()")
                ))

                if status_text and "sold" in status_text.lower():
                    continue

                sale_type = self.normalize_sale_type(status_text)

                self.seen_urls.add(url)

                try:
                    obj = self.parse_listing(url, property_sub_type, sale_type)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

        self.driver.quit()
        return self.results


    # ===================== LISTING ===================== #

    def parse_listing(self, url, property_sub_type, sale_type):


        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[@class='head_text']/h2"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//div[@class='head_text']/h2/text()")
        ))

        # ---------- DESCRIPTION ---------- #
        description_parts = tree.xpath(
            "//div[@class='content']//p//text()"
        )
        detailed_description = self._clean(" ".join(description_parts))

        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)


        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(detailed_description, sale_type)

        # ---------- IMAGES ---------- #
        property_images = [
            urljoin(self.DOMAIN, src)
            for src in tree.xpath(
                "//span[contains(@class,'frame')]//img/@src"
            )
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

        m = re.search(r'(\d+(?:\.\d+)?)\s*(sq\s*ft|sqft|sf)', text)
        if m:
            size_ft = str(int(float(m.group(1))))

        m = re.search(r'(\d+(?:\.\d+)?)\s*(acres?|acre|ac)', text)
        if m:
            size_ac = str(float(m.group(1)))

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
            "per annum", "pa", "pcm", "per month",
            "per week", "pw", "rent"
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

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        t = text.upper()
        m = re.search(FULL, t) or re.search(PARTIAL, t)
        return m.group() if m else ""

    def normalize_sale_type(self, status_text):
        if not status_text:
            return ""

        t = status_text.lower()

        if "let" in t:
            return "To Let"

        if "for sale" in t:
            return "For Sale"

        return ""


    def _clean(self, val):
        return " ".join(val.split()) if val else ""
