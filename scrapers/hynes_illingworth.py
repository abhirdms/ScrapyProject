import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class HynesIllingworthScraper:

    BASE_URL = "https://www.hynesillingworth.com/properties"
    DOMAIN = "https://www.hynesillingworth.com"
    AGENT_COMPANY = "Hynes Illingworth"

    def __init__(self):

        self.results = []
        self.seen_urls = set()

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        )
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")



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
            "//div[contains(@class,'property-card')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        property_blocks = tree.xpath(
            "//div[contains(@class,'property-card')]"
        )

        for block in property_blocks:

            relative_url = block.xpath(
                ".//a[contains(@class,'property-overlay')]/@href"
            )
            if not relative_url:
                continue

            listing_url = urljoin(self.DOMAIN, relative_url[0])

            if listing_url in self.seen_urls:
                continue

            self.seen_urls.add(listing_url)

            try:
                obj = self.parse_listing(listing_url, block)
                if obj:
                    self.results.append(obj)
            except Exception:
                continue

        self.driver.quit()
        return self.results

    # ============================================================
    # DETAIL PAGE
    # ============================================================

    def parse_listing(self, url, block):

        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//body"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------------- ADDRESS ----------------
        display_address = self._clean(" ".join(
            block.xpath(".//h4[contains(@class,'property-name')]/text()")
        ))


        # ---------------- IMAGE ----------------
        image_style = block.xpath(
            ".//div[contains(@class,'property-card-img')]/@style"
        )

        property_images = []
        if image_style:
            m = re.search(r'url\("(.*?)"\)', image_style[0])
            if m:
                property_images.append(m.group(1))


        # ---------------- DESCRIPTION ----------------
        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'property-detail') "
                "and not(contains(@class,'w-condition-invisible')) "
                "and not(.//h4[normalize-space()='Service Charge']) "
                "and not(.//h4[normalize-space()='Viewing'])]"
                "//text()[normalize-space()]"
            )
        ))

        # ---------------- AGENT DETAILS (FROM VIEWING SECTION) ----------------
        agent_name = ""
        agent_phone = ""
        agent_email = ""

        viewing_block = tree.xpath(
            "//div[contains(@class,'property-detail') and .//h4[normalize-space()='Viewing']]"
        )

        if viewing_block:
            block = viewing_block[0]

            # Extract FULL paragraph text (not only direct text nodes)
            lines = [
                self._clean(" ".join(p.xpath(".//text()")))
                for p in block.xpath(".//div[contains(@class,'w-richtext')]//p")
            ]

            for line in lines:

                lower_line = line.lower()

                # -------- NAME --------
                if lower_line.startswith("a:") or lower_line.startswith("attn"):
                    value = line.split(":", 1)[-1].strip()
                    agent_name = value.split(" or ")[0].strip()

                # -------- PHONE --------
                elif lower_line.startswith("t:") or lower_line.startswith("tel"):
                    value = line.split(":", 1)[-1].strip()
                    phones = re.findall(r'\d[\d\s]+', value)
                    if phones:
                        agent_phone = phones[0].strip()

                # -------- EMAIL --------
                elif lower_line.startswith("e:") or lower_line.startswith("mail"):
                    value = line.split(":", 1)[-1].strip()
                    emails = re.findall(r'[\w\.-]+@[\w\.-]+\.\w+', value)
                    if emails:
                        agent_email = emails[0].strip()




        # ---------------- SIZE ----------------
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------------- TENURE ----------------
        tenure = self.extract_tenure(detailed_description)

        # ---------------- SALE TYPE ----------------
        sale_type = self.normalize_sale_type(detailed_description)

        # ---------------- PRICE ----------------
        price = self.extract_numeric_price(detailed_description, sale_type)

        # ---------------- BROCHURE ----------------
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
        ]

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
            "agentCompanyName": self.AGENT_COMPANY,
            "agentCity": "",
            "agentName": agent_name,
            "agentEmail": agent_email,
            "agentPhone": agent_phone,
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }

        return obj

    # ============================================================
    # HELPERS
    # ============================================================

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(r'(\d+(?:\.\d+)?)\s*(sq\s*ft|sqft|sf)', text)
        if m:
            size_ft = float(m.group(1))

        m = re.search(r'(\d+(?:\.\d+)?)\s*(acres?|acre|ac)', text)
        if m:
            size_ac = float(m.group(1))

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):

        if sale_type != "For Sale":
            return ""

        if not text:
            return ""

        t = text.lower()

        if any(k in t for k in [
            "poa", "price on application", "subject to contract"
        ]):
            return ""

        if any(k in t for k in [
            "per annum", "pa", "pcm", "rent", "per month"
        ]):
            return ""

        m = re.search(r'£\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?', t)
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

    def normalize_sale_type(self, text):
        t = text.lower()
        if "for sale" in t:
            return "For Sale"
        if "to let" in t or "rent" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
