import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class FinchCommercialRealEstateScraper:
    BASE_URL = "https://finchcre.com/opportunities/"
    DOMAIN = "https://finchcre.com"

    def __init__(self):
        self.results = []
        self.seen_listing_urls = set()

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
            "//article[contains(@class,'elementor-post')]"
        )))

        tree = html.fromstring(self.driver.page_source)
        cards = tree.xpath("//article[contains(@class,'elementor-post')]")

        for card in cards:
            try:
                obj = self.parse_listing_card(card)
                if obj:
                    self.results.append(obj)
            except Exception:
                continue

        self.driver.quit()
        return self.results

    # ===================== LISTING CARD ===================== #

    def parse_listing_card(self, card):
        post_id = self._clean("".join(card.xpath("./@id")))
        listing_url = f"{self.BASE_URL}#{post_id}" if post_id else self.BASE_URL

        if listing_url in self.seen_listing_urls:
            return None
        self.seen_listing_urls.add(listing_url)

        raw_classes = " ".join(card.xpath("./@class"))
        card_text = self._clean(" ".join(card.xpath(".//text()")))
        if self.is_agreed_or_sold(raw_classes, card_text):
            return None

        display_address = self._clean(" ".join(
            card.xpath(".//h2[contains(@class,'elementor-heading-title')]//text()")
        ))
        area_text = self._clean(" ".join(
            card.xpath(
                ".//div[contains(@class,'elementor-widget-text-editor')]"
                "//div[contains(@class,'elementor-widget-container')]//text()"
            )
        ))

        if area_text:
            display_address = self._clean(" ".join(part for part in [display_address, area_text] if part))

        if not display_address:
            return None

        property_sub_type = self.extract_property_sub_type(raw_classes)

        pdf_links = [
            urljoin(self.DOMAIN, href)
            for href in card.xpath(".//a[contains(@href,'.pdf')]/@href")
            if href
        ]

        image_urls = self.extract_background_images(card)

        agent_email = self._clean("".join(card.xpath(".//a[starts-with(@href,'mailto:')]/@href")))
        agent_phone = self._clean("".join(card.xpath(".//a[starts-with(@href,'tel:')]/@href")))

        if agent_email.startswith("mailto:"):
            agent_email = agent_email.replace("mailto:", "", 1)

        if agent_phone.startswith("tel:"):
            agent_phone = agent_phone.replace("tel:", "", 1)

        detailed_description = self._clean(" ".join(
            part for part in [property_sub_type, display_address] if part
        ))

        sale_type = self.normalize_sale_type(" ".join(pdf_links + [raw_classes, detailed_description]))
        size_ft, size_ac = self.extract_size(detailed_description)
        tenure = self.extract_tenure(detailed_description)
        price = self.extract_numeric_price(detailed_description, sale_type)

        obj = {
            "listingUrl": listing_url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": image_urls,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": pdf_links,
            "agentCompanyName": "Finch Commercial Real Estate",
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

    def is_agreed_or_sold(self, class_string, card_text):
        haystack = f"{class_string} {card_text}".lower()
        blocked_patterns = [
            r"\bsold\b",
            r"\bsale\s+agreed\b",
            r"\blet\s+agreed\b",
            r"\bagreed\b",
            r"\bstc\b",
            r"\bsstc\b",
            r"\bunder\s+offer\b",
        ]
        return any(re.search(pattern, haystack) for pattern in blocked_patterns)

    def extract_property_sub_type(self, class_string):
        if not class_string:
            return ""

        matches = re.findall(r"property_listing_type-([a-z0-9-]+)", class_string.lower())
        if not matches:
            return ""

        normalized = []
        seen = set()
        for item in matches:
            value = item.replace("-", " ").strip().title()
            if value and value not in seen:
                normalized.append(value)
                seen.add(value)

        return ", ".join(normalized)

    def extract_background_images(self, node):
        style_text = " ".join(node.xpath(".//style//text()"))
        urls = re.findall(r"background-image\s*:\s*url\((['\"]?)(.*?)\1\)", style_text, flags=re.I)
        images = []
        for _, u in urls:
            clean = self._clean(u)
            if not clean:
                continue
            full = urljoin(self.DOMAIN, clean)
            if full not in images:
                images.append(full)
        return images

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
                sqm = min(a, b) if b else a
                size_ft = round(sqm * 10.7639, 3)

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac)",
            text,
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if not text:
            return ""

        if sale_type and sale_type.lower() != "for sale":
            return ""

        t = text.lower()

        if any(k in t for k in ["poa", "price on application", "upon application", "on application"]):
            return ""

        m = re.search(r"£\s*(\d+(?:,\d{3})*(?:\.\d+)?)(\s*m|\s*k)?", t)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))

        if m.group(2):
            if "m" in m.group(2):
                num *= 1_000_000
            if "k" in m.group(2):
                num *= 1_000

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

        if any(k in t for k in ["to let", "for lease", "lease", "to rent", "rental", "letting"]):
            return "To Let"

        if any(k in t for k in ["for sale", "sale", "rfs"]):
            return "For Sale"

        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
