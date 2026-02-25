import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from lxml import html


class CrosslandOtterHuntScraper:
    BASE_URL = "https://www.coh.eu/availability/"
    DOMAIN = "https://www.coh.eu"

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
            page_url = self.BASE_URL if page == 1 else f"{self.BASE_URL}page/{page}/"
            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//li[contains(@class,'property')]//h3/a"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)
            listing_urls = tree.xpath("//li[contains(@class,'property')]//h3/a/@href")

            if not listing_urls:
                break

            initial_count = len(self.seen_urls)

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

            # Stop if a page did not add any new URL (prevents duplicate-page loops)
            if len(self.seen_urls) == initial_count:
                break

            page += 1

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//section[contains(@class,'ph__title')]//h1"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self.extract_display_address(tree)
        intro_text = self.extract_intro_text(tree)
        description_text = self.extract_description(tree)
        detailed_description = self._clean(f"{intro_text} {description_text}")

        # ---------- SIZE ---------- #
        size_text = self.extract_available_area_text(tree)
        if not size_text:
            size_text = detailed_description
        size_ft, size_ac = self.extract_size(size_text)
        if not size_ft:
            size_ft = self.extract_sqft_from_table(tree)

        # ---------- SALE TYPE ---------- #
        sale_type_raw = self.extract_sale_type_text(tree, intro_text, description_text)
        sale_type = self.normalize_sale_type(sale_type_raw)

        # ---------- PRICE ---------- #
        raw_price_text = self.extract_table_price_text(tree)
        price = self.extract_numeric_price(raw_price_text, sale_type)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type = self.extract_property_sub_type(tree)

        # ---------- IMAGES ---------- #
        property_images = list(dict.fromkeys(
            tree.xpath("//div[contains(@class,'ph__carousel-images')]//img/@src")
        ))

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath(
                "//li[contains(@class,'action-brochure')]//a[contains(@href,'.pdf')]/@href"
            )
        ]

        # ---------- AGENT ---------- #
        agent_name = self._clean(" ".join(
            tree.xpath(
                "//h3[normalize-space()='Contact']"
                "/following-sibling::p/strong/text()"
            )
        ))

        agent_phone = self.extract_agent_phone(tree)

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
            "agentCompanyName": "Crossland Otter Hunt",
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

    # ===================== EXTRACTION HELPERS ===================== #

    def extract_display_address(self, tree):
        title = self._clean(" ".join(
            tree.xpath("//section[contains(@class,'ph__title')]//h1/text()")
        ))
        location = self._clean(" ".join(
            tree.xpath("//section[contains(@class,'ph__title')]//p/text()")
        ))
        return f"{title}, {location}" if location else title

    def extract_intro_text(self, tree):
        return self._clean(" ".join(
            tree.xpath("//div[contains(@class,'summary-contents')]//text()")
        ))

    def extract_description(self, tree):
        return self._clean(" ".join(
            tree.xpath(
                "(//div[contains(@class,'ph-main-description')]"
                "//div[contains(@class,'description')])[1]//text()"
            )
        ))

    def extract_available_area_text(self, tree):
        available_area_text = self._clean(" ".join(
            tree.xpath(
                "//p[strong[normalize-space()='Available Area']]"
                "/following-sibling::table[1]//text()"
            )
        ))
        if available_area_text:
            return available_area_text

        return self._clean(" ".join(
            tree.xpath(
                "//table[.//th[contains(normalize-space(),'Sq Ft')]]//text()"
            )
        ))

    def extract_sale_type_text(self, tree, intro_text, description_text):
        table_header_text = " ".join(
            tree.xpath(
                "//p[strong[normalize-space()='Available Area']]"
                "/following-sibling::table[1]//th//text()"
            )
        )

        rent_text = " ".join(
            tree.xpath(
                "//strong[normalize-space()='Available Area']"
                "/ancestor::div[1]//table//td[4]//text()"
            )
        )

        return self._clean(f"{table_header_text} {rent_text} {intro_text} {description_text}")

    def extract_table_price_text(self, tree):
        return self._clean(" ".join(
            tree.xpath(
                "//strong[normalize-space()='Available Area']"
                "/ancestor::div[1]//table//td[4]//text()"
            )
        ))

    def extract_property_sub_type(self, tree):
        class_values = tree.xpath(
            "//div[starts-with(@id,'property-')][1]/@class"
        )

        if not class_values:
            return ""

        class_text = class_values[0]
        match = re.search(r"commercial_property_type-([a-z0-9-]+)", class_text)
        if not match:
            return ""

        return match.group(1).replace("-", " ").title()

    def extract_sqft_from_table(self, tree):
        sqft_values = [
            self._clean(val)
            for val in tree.xpath(
                "//p[strong[normalize-space()='Available Area']]"
                "/following-sibling::table[1]//tbody//tr/td[2]//text()"
            )
            if self._clean(val)
        ]
        if not sqft_values:
            return ""

        raw = sqft_values[0].replace(",", "")
        if not re.fullmatch(r"\d+(?:\.\d+)?", raw):
            return ""

        return round(float(raw), 3)

    def extract_agent_phone(self, tree):
        lines = [
            self._clean(text)
            for text in tree.xpath(
                "//h3[normalize-space()='Contact']"
                "/following-sibling::p//text()[normalize-space()]"
            )
        ]
        phones = [line for line in lines if any(ch.isdigit() for ch in line)]
        return phones[0] if phones else ""

    # ===================== YOUR ORIGINAL METHODS ===================== #

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower()
        text = text.replace(",", "")
        text = text.replace("ft²", "sq ft")
        text = text.replace("m²", "sqm")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*feet)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        if not size_ft:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(sqm|sq\.?\s*m|m2|square\s*metres|square\s*meters)',
            text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm_value = min(a, b) if b else a
                size_ft = round(sqm_value * 10.7639, 3)

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac\.?)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        if not size_ac:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(hectares?|ha)',
                text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                hectare_value = min(a, b) if b else a
                size_ac = round(hectare_value * 2.47105, 3)

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
            "per month", "pw", "per week", "rent"
        ]):
            return ""

        m = re.search(r'[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?', t)
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

        text = text.upper()

        full_pattern = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        match = re.search(full_pattern, text)
        return match.group().strip() if match else ""

    def normalize_sale_type(self, text):
        t = text.lower()
        if any(k in t for k in ["for sale", "sale", "freehold", "long leasehold"]):
            return "For Sale"
        if any(k in t for k in [
            "rent", "to let", "letting", "assignment", "/ sqft", "sqft", "per sq ft"
        ]):
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
