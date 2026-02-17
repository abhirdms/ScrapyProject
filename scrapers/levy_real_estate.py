import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class LevyRealEstateScraper:
    BASE_URL = "https://www.levyrealestate.co.uk/properties"
    DOMAIN = "https://www.levyrealestate.co.uk"

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

    # ===================== RUN ===================== #

    def run(self):

        self.driver.get(self.BASE_URL)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'property-box')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            "//div[contains(@class,'property-box')]//a/@href"
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
            "//h1"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//h1[contains(@class,'h1-60')]/text()")
        ))

        # ---------- DESCRIPTION ---------- #
        detailed_description = self._clean(" ".join(
            tree.xpath("//ul/li[contains(@class,'wow')]/text()")
        ))

        # ---------- SIZE (SUM ALL FEATURES) ---------- #
        size_values = tree.xpath(
            "//div[@class='feature']/div[@class='value']/text()"
        )

        total_sqft = 0
        for val in size_values:
            clean_val = val.replace(",", "")
            m = re.search(r"(\d+(?:\.\d+)?)", clean_val)
            if m:
                total_sqft += float(m.group(1))

        size_ft = str(int(total_sqft)) if total_sqft else ""

        # ---------- IMAGES ---------- #
        property_images = [
            img.strip()
            for img in tree.xpath(
                "//div[contains(@class,'small-image-slide')]//a/@href"
            )
            if img.strip()
        ]

        # ---------- POSTCODE ---------- #
        postcode_text = self._clean(" ".join(
            tree.xpath("//h6[contains(@class,'address')]/text()")
        ))

        postcode = self.extract_postcode(postcode_text)

        # ---------- BROCHURE ---------- #
        brochure_urls = []
        brochure = tree.xpath(
            "//a[contains(@class,'brochure-btn')]/@href"
        )

        if brochure:
            pdf_url = brochure[0]
            if pdf_url.startswith("//"):
                pdf_url = "https:" + pdf_url
            brochure_urls.append(pdf_url)

        # ---------- AGENT DETAILS ---------- #
        agent_names = [
            self._clean(n)
            for n in tree.xpath(
                "//div[contains(@class,'team-member')]//h6[contains(@class,'name')]/text()"
            )
        ]

        agent_emails = [
            e.replace("mailto:", "").strip()
            for e in tree.xpath(
                "//div[contains(@class,'team-member')]//a[starts-with(@href,'mailto:')]/@href"
            )
        ]

        agent_phones = [
            self._clean(p)
            for p in tree.xpath(
                "//div[contains(@class,'team-member')]//p[contains(@class,'contacts')]/span[not(contains(@class,'icon-span'))]/text()"
            )
        ]

        # ---------- SALE TYPE (FROM GRID TAG) ---------- #
        sale_type_raw = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'property-box')]//div[contains(@class,'tag')]/text()"
            )
        ))

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": "",
            "propertySubType": "",
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": "",
            "postalCode": postcode,
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Levy Real Estate",
            "agentName": ", ".join(agent_names),
            "agentCity": "",
            "agentEmail": ", ".join(agent_emails),
            "agentPhone": ", ".join(agent_phones),
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": "",
            "saleType": sale_type_raw,
        }

        return obj

    # ===================== HELPERS ===================== #

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
