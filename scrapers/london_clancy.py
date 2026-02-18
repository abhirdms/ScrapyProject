import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class LondonClancyScraper:
    BASE_URL = "https://search.curchodandco.com/properties/"
    DOMAIN = "https://search.curchodandco.com"

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
            page_url = f"{self.BASE_URL}?page={page}"
            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'propItemWrap')]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            listing_urls = tree.xpath(
                "//div[contains(@class,'propItemWrap')]"
                "//a[contains(@href,'/properties/')][1]/@href"
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
            "//div[contains(@class,'propTitle')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'propTitle')]"
                "/p[@class='lead']/text()"
            )
        ))

        # ---------- SALE TYPE ---------- #
        sale_type_raw = self._clean(" ".join(
            tree.xpath(
                "//tr[td[normalize-space()='Tenure']]/td[2]/text()"
            )
        ))

        sale_type = self.normalize_sale_type(sale_type_raw)

        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type = self._clean(" ".join(
            tree.xpath(
                "//tr[td[normalize-space()='Property Type']]/td[2]/text()"
            )
        ))

        # ---------- DESCRIPTION ---------- #
        description_parts = []

        sections = tree.xpath("//div[contains(@class,'post')]//h2")

        for section in sections:
            heading = self._clean(" ".join(section.xpath(".//text()")))

            content_nodes = section.xpath(
                "following-sibling::*["
                "count(. | following-sibling::h2[1]/preceding-sibling::*) = "
                "count(following-sibling::h2[1]/preceding-sibling::*)"
                "]//text()"
            )

            content = self._clean(" ".join(content_nodes))

            if heading:
                description_parts.append(heading)

            if content:
                description_parts.append(content)

        detailed_description = "\n\n".join(description_parts)


        # ---------- SIZE ---------- #
        size_text = self._clean(" ".join(
            tree.xpath(
                "//tr[td[normalize-space()='Size']]/td[2]/text()"
            )
        ))

        size_ft, size_ac = self.extract_size(size_text)

        # ---------- TENURE ---------- #
        tenure_text = self._clean(" ".join(
            tree.xpath(
                "//h2[normalize-space()='Terms']"
                "/following-sibling::p[1]//text()"
            )
        ))

        tenure = self.extract_tenure(tenure_text)


        # ---------- PRICE (RENT ROW AS PROVIDED) ---------- #
        price_text = self._clean(" ".join(
            tree.xpath(
                "//tr[td[normalize-space()='Rent']]/td[2]/text()"
            )
        ))

        price = self.extract_numeric_price(price_text, sale_type)

        # ---------- IMAGES ---------- #
        property_images = [
            src for src in tree.xpath(
                "//div[contains(@class,'slick-slide') "
                "and not(contains(@class,'slick-cloned'))]"
                "//img/@src"
            ) if src
        ]

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
        ]

        # ---------- AGENT ---------- #
        agent_name = self._clean(" ".join(
            tree.xpath(
                "(//div[contains(@class,'contactUser__details')])[1]"
                "//h3/a/text()"
            )
        ))

        agent_phone = self._clean(" ".join(
            tree.xpath(
                "(//div[contains(@class,'contactUser__details')])[1]"
                "//p[1]/text()"
            )
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
            "agentCompanyName": "London Clancy",
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

    def extract_tenure(self, text):
        if not text:
            return ""

        t = text.lower()

        if "freehold" in t:
            return "Freehold"

        if "leasehold" in t:
            return "Leasehold"

        return ""


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

        # ===================== SQUARE FEET ===================== #
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*feet)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        # ===================== SQUARE METRES ===================== #
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
                size_ft = round(sqm_value * 10.7639, 3)  # convert sqm → sqft

        # ===================== ACRES ===================== #
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac\.?)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        # ===================== HECTARES ===================== #
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
                size_ac = round(hectare_value * 2.47105, 3)  # convert ha → acres

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale":
            return ""

        if not text:
            return ""

        t = text.lower()

        # Ignore POA types
        if any(k in t for k in [
            "poa", "price on application", "upon application", "on application"
        ]):
            return ""

        # 🔥 IMPORTANT FIX:
        # Only extract the part BEFORE "or to let"
        sale_part = t.split("or to let")[0]

        # Remove VAT text
        sale_part = sale_part.replace("plus vat", "")

        # Find first £ amount in sale portion
        m = re.search(r'£\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?', sale_part)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))

        # Handle million shorthand
        if "m" in m.group(0):
            num *= 1_000_000

        return str(int(num))

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
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
