import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class EmbersonCoScraper:
    BASE_URL = "https://www.emberson.com/?s=&post_type=listing&propertytype=&county=&tenure=&propertysize="
    DOMAIN = "https://www.emberson.com"

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
        page = 1

        while True:
            page_url = self.BASE_URL if page == 1 else f"{self.BASE_URL}&paged={page}"
            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'listing-wrap')]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            listing_urls = tree.xpath(
                "//div[contains(@class,'listing-wrap')]"
                "//a[contains(@href,'/listings/')]/@href"
            )

            if not listing_urls:
                break

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

            page += 1

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h1[contains(@class,'entry-title')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//h1[@class='entry-title']/text()")
        ))

        # ---------- SALE TYPE ---------- #
        article_class = " ".join(
            tree.xpath("//article[contains(@class,'listing')]/@class")
        )

        sale_type = ""
        m = re.search(r'tenure-([a-z\-]+)', article_class)
        if m:
            raw = m.group(1)
            if raw in ["for-sale", "under-offer"]:
                sale_type = "For Sale"
            elif raw == "to-let":
                sale_type = "To Let"

        # ---------- PROPERTY SUB TYPE ---------- #
        property_types = re.findall(
            r'propertytype-([a-zA-Z0-9\-]+)',
            article_class
        )
        property_sub_type = ", ".join(
            pt.replace("-", " ").title() for pt in property_types
        )

        # ---------- PROPERTY DETAILS BLOCK ---------- #
        property_details_block = tree.xpath(
            "//div[contains(@class,'property-details')]"
        )
        property_details_tree = property_details_block[0] if property_details_block else None

        # ---------- PRICE ---------- #
        price_text = ""
        if property_details_tree is not None:
            price_text = self._clean(" ".join(
                property_details_tree.xpath(
                    ".//b[text()='Price:']/following-sibling::text()[1]"
                )
            ))

        price = self.extract_numeric_price(price_text, sale_type)

        # ---------- TENURE (ONLY FROM PROPERTY DETAILS) ---------- #
        tenure = ""
        if property_details_tree is not None:
            tenure = self._clean(" ".join(
                property_details_tree.xpath(
                    ".//b[text()='Tenure:']/following-sibling::text()[1]"
                )
            ))

        # ---------- SIZE (ONLY FROM PROPERTY DETAILS) ---------- #
        size_ft = ""
        size_ac = ""

        if property_details_tree is not None:

            size_text = self._clean(" ".join(
                property_details_tree.xpath(
                    ".//b[contains(text(),'Approx. Sq Feet')]"
                    "/following-sibling::text()[1]"
                )
            ))

            if size_text:
                size_ft, size_ac = self.extract_size(size_text)

            if not size_ft:
                sqm_text = self._clean(" ".join(
                    property_details_tree.xpath(
                        ".//b[contains(text(),'Approx Sq Meters')]"
                        "/following-sibling::text()[1]"
                    )
                ))
                size_ft, size_ac = self.extract_size(sqm_text)

        # ---------- DESCRIPTION ---------- #
        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//div[@class='entry-content']/p"
                "[not(ancestor::span) and not(contains(.,'DISCLAIMER'))]"
                "//text()"
            )
        ))

        # ---------- IMAGES ---------- #
        property_images = [
            img for img in tree.xpath(
                "//div[@class='entry-content']//a[contains(@href,'/uploads/')]/@href"
            ) if img
        ]

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
        ]

        # ---------- AGENT DETAILS ---------- #
        agent_email = ""
        email_raw = tree.xpath("//a[starts-with(@href,'mailto:')]/@href")
        if email_raw:
            agent_email = email_raw[0].replace("mailto:", "").strip()

        # ---------- AGENT PHONE (DEDUPED) ---------- #
        phones = tree.xpath(
            "//b[contains(text(),'Tel')]/following-sibling::text()[1]"
        )

        cleaned_phones = []
        for p in phones:
            p = self._clean(p)
            if p and p not in cleaned_phones:
                cleaned_phones.append(p)

        agent_phone = cleaned_phones[0] if cleaned_phones else ""

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
            "agentCompanyName": "Emberson & Co",
            "agentName": "",
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

        text = text.lower()
        text = text.replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        # Handles: 1250-2500 OR 1250 to 2500 OR 1250
        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?', text)
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
            "poa", "price on application", "upon application"
        ]):
            return ""

        if any(k in t for k in [
            "per annum", "pa", "pcm", "rent", "pax"
        ]):
            return ""

        m = re.search(r'[£]\s*(\d+(?:,\d{3})*(?:\.\d+)?)', t)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))
        return str(int(num))

    def extract_postcode(self, text: str):
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