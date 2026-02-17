import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class JaggardMaclandScraper:
    BASE_URL = "https://jaggardmacland.co.uk/properties"
    DOMAIN = "https://jaggardmacland.co.uk"

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

        visited_pages = set()
        next_page_url = self.BASE_URL

        while next_page_url and next_page_url not in visited_pages:

            visited_pages.add(next_page_url)

            self.driver.get(next_page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//article[contains(@class,'compactCard')]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            listing_nodes = tree.xpath("//article[contains(@class,'compactCard')]")
            if not listing_nodes:
                break

            for node in listing_nodes:

                href = node.xpath(".//a[@class='card']/@href")
                if not href:
                    continue

                url = urljoin(self.DOMAIN, href[0])

                if url in self.seen_urls:
                    continue
                self.seen_urls.add(url)

                raw_sale_type = " ".join(
                    node.xpath(".//span[contains(@class,'overTag')]/text()")
                )
                sale_type = self.normalize_sale_type(raw_sale_type)

                tags = node.xpath(".//span[contains(@class,'tag')]/text()")
                property_sub_type = ", ".join([
                    self._clean(t) for t in tags if t.strip()
                ])

                try:
                    obj = self.parse_listing(url, sale_type, property_sub_type)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

            # ---- NEXT PAGE ----
            next_link = tree.xpath("//a[contains(@class,'js-loadMore')]/@href")

            if next_link:
                candidate_url = urljoin(self.DOMAIN, next_link[0])

                # Stop if same page or already visited
                if candidate_url == next_page_url or candidate_url in visited_pages:
                    break

                next_page_url = candidate_url
            else:
                break

        self.driver.quit()
        return self.results


    # ===================== LISTING ===================== #

    def parse_listing(self, url, sale_type, property_sub_type):

        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[@class='withGutters']//header//h1"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ----------
        display_address = self._clean(" ".join(
            tree.xpath("//div[@class='withGutters']//header//h1/text()")
        ))

        # ---------- HEADER META ----------
        header_meta = tree.xpath(
            "//div[@class='withGutters']//header//p[@class='meta'][2]/text()"
        )
        price_text = " ".join(header_meta)

        # ---------- PRICE ----------
        price = self.extract_numeric_price(price_text, sale_type)

        # ---------- SIZE ----------
        size_ft, size_ac = self.extract_size(price_text)

        # ---------- DESCRIPTION ----------
        detailed_description = self._clean(" ".join(
            tree.xpath("//h2[text()='Property details']/following-sibling::p//text()")
        ))

        # Include header text for tenure detection
        combined_description = self._clean(f"{price_text} {detailed_description}")
        tenure = self.extract_tenure(combined_description)

        # ---------- IMAGES ----------
        property_images = [
            urljoin(self.DOMAIN, src)
            for src in tree.xpath(
                "//div[contains(@class,'slick-track')]"
                "//img[contains(@class,'carouselMainImg')]/@src"
            )
        ]

        # ---------- BROCHURE (DEDUPLICATED) ----------
        brochure_urls = list({
            urljoin(self.DOMAIN, href)
            for href in tree.xpath(
                "//a[contains(@href,'.pdf') and contains(translate(text(),'BROCHURE','brochure'),'brochure')]/@href"
            )
        })

        # ---------- AGENT (FIRST ONLY) ----------
        agent_block = tree.xpath(
            "(//div[contains(@class,'flex') and contains(@class,'itemsCenter')])[1]"
        )

        agent_name = ""
        agent_email = ""
        agent_phone = ""

        if agent_block:
            block = agent_block[0]

            agent_name = self._clean(" ".join(
                block.xpath(".//h3/text()")
            ))

            agent_email = self._clean(" ".join(
                block.xpath(".//a[starts-with(@href,'mailto:')]/text()")
            ))

            agent_phone = self._clean(" ".join(
                block.xpath(".//a[starts-with(@href,'tel:')]/text()")
            ))

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
            "agentCompanyName": "Jaggard Macland",
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

    def normalize_sale_type(self, text):
        t = text.lower()
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(r'(\d+(?:\.\d+)?)\s*(sq\s*ft|sqft|sf)', text)
        if m:
            size_ft = round(float(m.group(1)), 3)

        m = re.search(r'(\d+(?:\.\d+)?)\s*(sqm|sq\s*m|m2|m²)', text)
        if m:
            size_ft = round(float(m.group(1)) * 10.7639, 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if not text:
            return ""

        if sale_type != "For Sale":
            return ""

        t = text.lower()

        if any(x in t for x in [
            "poa", "price on application", "upon application",
            "on application", "subject to contract"
        ]):
            return ""

        if "per annum" in t or "per year" in t:
            return ""

        matches = re.findall(r'£\s*(\d+(?:,\d{3})*)', text)
        if not matches:
            return ""

        return matches[0].replace(",", "")

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

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
