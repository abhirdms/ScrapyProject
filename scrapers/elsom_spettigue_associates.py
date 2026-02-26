import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class ElsomSpettigueAssociatesScraper:
    BASE_URL = "https://www.esassociates.co.uk/properties/"
    DOMAIN = "https://www.esassociates.co.uk"
    AGENT_COMPANY = "Elsom Spettigue Associates"

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

            if page > 1 and self.driver.current_url.rstrip("/") == self.BASE_URL.rstrip("/"):
                break

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//article[contains(@class,'w-grid-item') and contains(@class,'property')]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            listing_urls = tree.xpath(
                "//article[contains(@class,'w-grid-item') and contains(@class,'property')]"
                "//h4[contains(@class,'post_title')]//a/@href"
            )

            if not listing_urls:
                break

            new_urls_on_page = 0

            for href in listing_urls:
                url = urljoin(self.DOMAIN, href)

                if url in self.seen_urls:
                    continue
                self.seen_urls.add(url)
                new_urls_on_page += 1

                try:
                    obj = self.parse_listing(url)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

            if new_urls_on_page == 0:
                break

            page += 1

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h1[contains(@class,'post_title')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//h1[contains(@class,'post_title')]/text()")
        ))

        # ---------- SALE TYPE (HELPER-DRIVEN) ---------- #
        sale_type_raw = self._clean(" ".join(
            tree.xpath(
                "//nav[contains(@class,'g-breadcrumbs')]"
                "//a[contains(@href,'listing-type')]//span/text()"
            )
        )) or display_address
        sale_type = self.normalize_sale_type(sale_type_raw)

        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type = self._clean(" ".join(
            tree.xpath(
                "//meta[@itemprop='propertySubType']/@content | "
                "//meta[@itemprop='category']/@content"
            )
        ))

        overview_text = self.get_section_text(tree, "Overview")
        location_text = self.get_section_text(tree, "Location")
        accommodation_text = self.get_section_text(tree, "Accommodation")
        business_rates_text = self.get_section_text(tree, "Business Rates")
        planning_text = self.get_section_text(tree, "Planning Information")
        terms_text = self.get_section_text(tree, "Terms")
        vat_text = self.get_section_text(tree, "VAT Information")

        detailed_description = " ".join(
            part for part in [
                overview_text,
                location_text,
                accommodation_text,
                business_rates_text,
                planning_text,
                terms_text,
                vat_text,
            ] if part
        )

        # ---------- SIZE ---------- #
        structured_size = self._clean(" ".join(
            tree.xpath("//span[contains(@class,'sqft-conversion')]/text()")
        ))

        size_ft, size_ac = self.extract_size(
            " ".join([structured_size, detailed_description])
        )

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- PRICE (ONLY IF FOR SALE) ---------- #
        price_text = self._clean(" ".join(
            tree.xpath(
                "//span[contains(@class,'property-rent')]//span/text() | "
                "//div[contains(@class,'terms')]//text()"
            )
        ))
        price = self.extract_numeric_price(price_text, sale_type)

        # ---------- IMAGES ---------- #
        property_images = list(dict.fromkeys([
            src for src in tree.xpath(
                "//img[contains(@class,'rsMainSlideImage')]/@src | "
                "//div[contains(@class,'w-slider')]//img/@src"
            ) if src and src.startswith("http")
        ]))

        # ---------- BROCHURE ---------- #
        brochure_urls = list(dict.fromkeys([
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
        ]))

        # ---------- AGENT EMAIL ---------- #
        agent_email_links = tree.xpath(
            "//a[starts-with(@href,'mailto:')]/@href"
        )
        agent_email = ""
        if agent_email_links:
            agent_email = self._clean(agent_email_links[0]).replace("mailto:", "")

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
            "agentEmail": agent_email,
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }

        return obj

    # ===================== HELPERS ===================== #

    def get_section_text(self, tree, heading):
        section_text = self._clean(" ".join(
            tree.xpath(
                f"//div[contains(@class,'w-post-elm')][.//h2[normalize-space()='{heading}']]"
                "//p//text()"
            )
        ))

        if section_text:
            return section_text

        return self._clean(" ".join(
            tree.xpath(
                f"//h2[normalize-space()='{heading}']/following::p[1]//text()"
            )
        ))

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

        # SQUARE FEET
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf|square\s*feet|sq\s*feet)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        # SQUARE METRES → CONVERT
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

        # ACRES
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac\.?)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        # HECTARES → CONVERT
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
        partial_pattern = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        match = re.search(full_pattern, text)
        if match:
            return match.group().strip()

        match = re.search(partial_pattern, text)
        return match.group().strip() if match else ""

    def normalize_sale_type(self, text):
        t = text.lower()
        if "for-sale" in t or "/sale/" in t or "for sale" in t or "sale" in t:
            return "For Sale"
        if "to-let" in t or "/let/" in t or "to let" in t or "rent" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
