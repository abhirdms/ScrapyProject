import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class CyrilLeonardScraper:
    BASE_URL = "https://www.cyrilleonard.com/instructions/current-sales/"
    DOMAIN = "https://www.cyrilleonard.com"
    DETAIL_COL_XPATH = (
        "//section[contains(@class,'content')]"
        "//div[contains(@class,'col-12') and contains(@class,'col-lg-5') and contains(@class,'col-md-6')][1]"
    )

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
            "//article[contains(@class,'instruction') and .//h3/a]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_cards = tree.xpath("//article[contains(@class,'instruction') and .//h3/a]")

        for card in listing_cards:
            href = self._first_clean(card.xpath(".//h3/a/@href | .//a[@href][1]/@href"))
            if not href:
                continue

            url = urljoin(self.DOMAIN, href)

            if url in self.seen_urls:
                continue
            self.seen_urls.add(url)

            listing_meta = {
                "title": self._first_clean(card.xpath(".//h3/a/text()")),
                "location": self._clean(" ".join(card.xpath(".//h3[contains(@class,'text-secondary')]/text()"))),
                "size": self._extract_table_value(card, "size"),
                "value": self._extract_table_value(card, "value"),
                "card_image": self._first_clean(card.xpath(".//img/@data-lazy-src | .//img/@src")),
            }

            try:
                obj = self.parse_listing(url, listing_meta)
                if obj:
                    self.results.append(obj)
            except Exception:
                continue

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url, listing_meta=None):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//main//h1 | //section[contains(@class,'content')]"
        )))

        tree = html.fromstring(self.driver.page_source)
        listing_meta = listing_meta or {}
        detail_col_text = self._clean(" ".join(tree.xpath(
            f"{self.DETAIL_COL_XPATH}//text()"
        )))

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._first_clean(tree.xpath("//h1/text()"))
        if not display_address:
            display_address = self._first_clean(tree.xpath("//meta[@property='og:title']/@content"))
        if not display_address:
            display_address = self._first_clean(tree.xpath("//title/text()"))
        if not display_address:
            display_address = listing_meta.get("title", "")
        display_address = self._strip_site_suffix(display_address)

        # ---------- SALE TYPE ---------- #
        sale_type_hints = " ".join(filter(None, [
            listing_meta.get("value", ""),
            listing_meta.get("location", ""),
            detail_col_text,
        ]))
        sale_type = self.normalize_sale_type(sale_type_hints)

        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(listing_meta.get("value", ""), sale_type)
        if not price:
            price = self.extract_numeric_price(self._extract_detail_table_value(tree, "value"), sale_type)
        if not price:
            price = self.extract_numeric_price(detail_col_text, sale_type)

        # ---------- PROPERTY SUB TYPE ---------- #
        property_type_text = self._clean(" ".join(tree.xpath(
            f"{self.DETAIL_COL_XPATH}//td[contains(@class,'text-dark-blue') and contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'type')]"
            "/following-sibling::td[1]//text()"
        )))
        property_sub_type = self.extract_property_sub_type(property_type_text or detail_col_text)

        # ---------- DESCRIPTION ---------- #
        description_parts = tree.xpath(
            f"{self.DETAIL_COL_XPATH}//ul[1]//li//text()"
            f" | {self.DETAIL_COL_XPATH}//h3[1]//span//text()"
            f" | {self.DETAIL_COL_XPATH}//p//text()"
        )
        detailed_description = self._clean(" ".join(description_parts))
        if not detailed_description:
            detailed_description = self._first_clean(
                tree.xpath("//meta[@name='description']/@content")
            )

        # ---------- SIZE ---------- #
        size_sources = [
            listing_meta.get("size", ""),
            self._extract_detail_table_value(tree, "size"),
            detailed_description,
            detail_col_text,
        ]
        size_ft, size_ac = self.extract_size(" ".join(filter(None, size_sources)))

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(" ".join([detailed_description, detail_col_text]))

        # ---------- IMAGES ---------- #
        images = tree.xpath(
            "//div[contains(@class,'internal-big-images')]"
            "//div[contains(@class,'slide') and not(contains(@class,'slick-cloned'))]//img/@src"
            " | //div[contains(@class,'gallery-container')]//img/@src"
            " | //meta[@property='og:image']/@content"
        )
        property_images = []
        for img in images:
            absolute_img = urljoin(self.DOMAIN, img)
            if absolute_img and absolute_img not in property_images:
                property_images.append(absolute_img)

        if not property_images and listing_meta.get("card_image"):
            property_images = [urljoin(self.DOMAIN, listing_meta["card_image"])]

        # ---------- BROCHURE ---------- #
        brochure_urls = []
        for href in tree.xpath(f"{self.DETAIL_COL_XPATH}//a[contains(@href,'.pdf')]/@href"):
            brochure = urljoin(self.DOMAIN, href)
            if brochure not in brochure_urls:
                brochure_urls.append(brochure)

        # ---------- AGENT DETAILS ---------- #
        agent_name = self._first_clean(tree.xpath(
            f"{self.DETAIL_COL_XPATH}//div[contains(@class,'contact')]//a[contains(@href,'/our-people/profile/')]"
            "//h3[contains(@class,'text-dark-blue')]/text()"
        ))
        if not agent_name:
            agent_name = self._clean(" ".join(
                tree.xpath("//div[contains(@class,'call-agent')]/h5/text()")
            ))

        agent_email = self._extract_agent_email(tree)

        agent_phone = tree.xpath("//a[starts-with(@href,'tel:')]/@href")
        agent_phone = agent_phone[0].replace("tel:", "").strip() if agent_phone else ""

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
            "agentCompanyName": "Cyril Leonard",
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

    def _extract_table_value(self, card, key_name):
        value = card.xpath(
            ".//tr[td[1][contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '%s')]]/td[2]//text()"
            % key_name
        )
        return self._clean(" ".join(value))

    def _extract_detail_table_value(self, tree, key_name):
        value = tree.xpath(
            f"{self.DETAIL_COL_XPATH}//tr[td[1][contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{key_name}')]]/td[2]//text()"
        )
        return self._clean(" ".join(value))

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
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*feet)",
            text,
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        if not size_ft:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
                r"(sqm|sq\.?\s*m|m2|square\s*metres|square\s*meters)",
                text,
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm_value = min(a, b) if b else a
                size_ft = round(sqm_value * 10.7639, 3)

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(acres?|acre|ac\.?)",
            text,
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        if not size_ac:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
                r"(hectares?|ha)",
                text,
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
            "poa", "price on application", "upon application", "on application",
            "offers invited", "unconditional offers",
        ]):
            return ""

        if any(k in t for k in [
            "per annum", "pa", "per year", "pcm",
            "per month", "pw", "per week", "rent", "to let"
        ]):
            return ""

        m = re.search(r"[£€]\s*([\d\.,]+)\s*m?", t)
        if not m:
            return ""

        raw = m.group(1).strip()
        if "," in raw and "." in raw:
            # Handle formats like 7.900,000 or 7,900.000
            raw = raw.replace(",", "").replace(".", "")
        else:
            raw = raw.replace(",", "")
            if raw.count(".") > 1:
                raw = raw.replace(".", "")
        try:
            num = float(raw)
        except ValueError:
            return ""

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

        full_pattern = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b"
        partial_pattern = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\b"

        match = re.search(full_pattern, text)
        if match:
            return match.group().strip()

        match = re.search(partial_pattern, text)
        return match.group().strip() if match else ""

    def normalize_sale_type(self, text):
        t = (text or "").lower()

        if any(k in t for k in [
            "sale", "offers", "value", "guide price", "asking price", "investment"
        ]):
            return "For Sale"
        if any(k in t for k in [
            "to let", "letting", "rent", "per annum", "per month", "pcm", "pa"
        ]):
            return "To Let"

        return ""

    def extract_property_sub_type(self, text):
        if not text:
            return ""

        t = text.lower()
        mapping = [
            ("office", "Office"),
            ("retail", "Retail"),
            ("industrial", "Industrial"),
            ("warehouse", "Industrial"),
            ("land", "Land"),
            ("leisure", "Leisure"),
            ("investment", "Investment"),
            ("mixed use", "Mixed Use"),
            ("development", "Development"),
            ("hotel", "Leisure"),
        ]
        for key, value in mapping:
            if key in t:
                return value
        return ""

    def _extract_agent_email(self, tree):
        mailto_links = tree.xpath("//a[starts-with(@href,'mailto:')]/@href")
        for href in mailto_links:
            clean = href.replace("mailto:", "").strip()
            lower = clean.lower()
            if "@" in clean and "subject=" not in lower and "body=" not in lower:
                return clean
        return ""

    def _strip_site_suffix(self, text):
        if not text:
            return ""
        text = re.sub(r"\s*-\s*cyril\s+leonard\s*$", "", text, flags=re.I)
        text = re.sub(r"\s*\|\s*cyril\s+leonard\s*$", "", text, flags=re.I)
        return self._clean(text)

    def _first_clean(self, values):
        for value in values:
            clean_value = self._clean(value)
            if clean_value:
                return clean_value
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
