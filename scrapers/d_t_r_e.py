import re
from urllib.parse import urljoin, urlparse, parse_qs

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class DTREScraper:
    BASE_URL = "https://dtre.com/search/properties"
    DOMAIN = "https://dtre.com"

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
            page_url = self.BASE_URL if page == 1 else f"{self.BASE_URL}?page={page}"
            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//section[contains(@class,'property-listing-results')]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            listing_urls = tree.xpath(
                "//section[contains(@class,'property-listing-results')]"
                "//div[contains(@class,'card')]"
                "//a[contains(@class,'card__link')]/@href"
            )

            if not listing_urls:
                break

            for url in listing_urls:
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
            "//div[contains(@class,'propertypage')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        title = self._clean(" ".join(
            tree.xpath("//main//h1/text()")
        ))

        address = self._clean(" ".join(
            tree.xpath("//main//address/text()")
        ))

        display_address = self._clean(
            ", ".join(part for part in [title, address] if part)
        )

        # ---------- SALE TYPE ---------- #
        sale_type_raw = self._clean(" ".join(
            tree.xpath(
                "//table[contains(@class,'availability__block')]"
                "//tr[td[normalize-space()='Tenure']]/td[2]/text()"
            )
        ))

        sale_type = self.normalize_sale_type(sale_type_raw)

        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type = self._clean(" ".join(
            tree.xpath(
                "//table[contains(@class,'availability__block')]"
                "//tr[td[normalize-space()='Property Type']]/td[2]/text()"
            )
        ))

        # ---------- DESCRIPTION ---------- #
        description_parts = tree.xpath(
            "//h4[normalize-space()='Description']"
            "/following-sibling::p//text()"
        )

        detailed_description = self._clean(" ".join(description_parts))


        size_text_table = self._clean(" ".join(
            tree.xpath(
                "//table[contains(@class,'availability__block')]"
                "//tr[td[normalize-space()='Size']]/td[2]/text()"
            )
        ))

        combined_size_text = size_text_table if size_text_table else detailed_description

        size_ft, size_ac = self.extract_size(combined_size_text)


        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(description_parts)

        # ---------- PRICE ---------- #
        price_text = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'price-per-month')]"
                "//span[contains(@class,'propText__price-rent')]/text()"
            )
        ))

        if not price_text:
            price_text = self._clean(" ".join(
                tree.xpath(
                    "//table[contains(@class,'availability__block')]"
                    "//tr[td[normalize-space()='Rent']]/td[2]/text()"
                )
            ))

        price = self.extract_numeric_price(price_text + " " + detailed_description , sale_type)

        # ---------- HERO IMAGE ---------- #
        style_attr = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'hero-image')]"
                "//div[contains(@class,'image')]/@style"
            )
        ))

        property_images = []
        if style_attr:
            m = re.search(r'url\((.*?)\)', style_attr)
            if m:
                property_images.append(m.group(1))

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            href for href in tree.xpath(
                "//a[contains(@data-file_id,'marketing_brochure')]/@href"
            )
        ]

        # ---------- AGENT DETAILS (FIRST AGENT ONLY) ---------- #
        agent_name = self._clean(" ".join(
            tree.xpath(
                "(//div[contains(@class,'contactUser')]"
                "//div[contains(@class,'contactUser__details')]/p[1]/text())[1]"
            )
        ))

        agent_phone = self._clean(" ".join(
            tree.xpath(
                "(//div[contains(@class,'contactUser')]"
                "//p[contains(text(),'T:')]/text())[1]"
            )
        )).replace("T:", "").strip()

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
            "agentCompanyName": "DTRE",
            "agentName": agent_name,
            "agentCity": "",
            "agentEmail": "",
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

        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*sq', text)
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
            "poa", "price on application", "upon application", "on application"
        ]):
            return ""

        if any(k in t for k in [
            "per annum", "pa", "per year", "pcm",
            "per month", "pw", "rent", "per sq ft"
        ]):
            return ""

        m = re.search(r'£\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?', t)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))
        if "m" in m.group(0):
            num *= 1_000_000

        return str(int(num))

    def extract_postcode(self, text):
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
    
    def extract_tenure(self, text_parts):
        text = " ".join(text_parts).lower()
        if "freehold" in text:
            return "Freehold"
        if "leasehold" in text:
            return "Leasehold"
        return ""

    def normalize_sale_type(self, text):
        t = text.lower()
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""