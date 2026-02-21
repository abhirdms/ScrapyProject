import re
import time
import hashlib
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class ReddinClancyCoScraper:
    BASE_URL = "https://www.reddin-clancy.co.uk/our-property/"
    DOMAIN = "https://www.reddin-clancy.co.uk"

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
            "//div[@class='search-results-row']"
        )))

        self._load_all_listing_cards()
        cards = self.driver.find_elements(By.CSS_SELECTOR, "div.search-results-row")

        for card in cards:
            try:
                obj = self.parse_listing_card(card)
                if obj:
                    self.results.append(obj)
            except Exception:
                continue

        self.driver.quit()
        return self.results

    def parse_listing_card(self, card):
        card_html = card.get_attribute("outerHTML") or ""
        if not card_html:
            return None
        card = html.fromstring(card_html)

        sale_status = self._clean(" ".join(
            card.xpath(
                ".//li[contains(.,'Sale Status')]/span/text()"
                " | .//span[contains(@class,'features-mark-status')]/text()"
            )
        )).lower()
        if "sold" in sale_status:
            return None

        features = self._extract_features_map(card)

        href = self._clean(" ".join(card.xpath("./@data-href")))
        if not href:
            href = self._clean(" ".join(
                card.xpath(".//a[contains(@href,'propertydetails')][1]/@href")
            ))
        title = self._first_text(card, [
            ".//div[contains(@class,'property-features')][1]//h2/text()",
            ".//h2/text()",
        ])
        subtitle = self._first_text(card, [
            ".//div[contains(@class,'property-features')][1]//h3/text()",
            ".//h3/text()",
        ])
        display_address = subtitle or title

        property_sub_type = features.get("property type", "")
        sale_type_raw = features.get("sale type", "")
        sale_type = self.normalize_sale_type(sale_type_raw)

        quote_price_text = features.get("quote price", "")
        price = self.extract_numeric_price(quote_price_text, sale_type)

        href = re.sub(r"propertydetails/propertydetails", "propertydetails", href)
        if href:
            listing_url = urljoin(self.DOMAIN, href)
        else:
            fallback_key = "|".join([display_address, property_sub_type, quote_price_text, sale_type])
            digest = hashlib.md5(fallback_key.encode("utf-8")).hexdigest()[:12]
            listing_url = f"{self.BASE_URL}#listing-{digest}"

        if listing_url in self.seen_urls:
            return None
        self.seen_urls.add(listing_url)

        size_text = self._clean(" ".join(
            card.xpath(".//span[contains(@class,'search-property-size')]/text()")
        ))
        size_ft, size_ac = self.extract_size(size_text)

        image_style = self._clean(" ".join(
            card.xpath(".//div[contains(@class,'search-results-row-thumb')]//a[1]/@style")
        ))
        property_images = []
        if image_style:
            m = re.search(r"url\(['\"]?([^'\")]+)", image_style)
            if m:
                property_images = [urljoin(self.DOMAIN, m.group(1))]

        obj = {
            "listingUrl": listing_url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": "",
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": [],
            "agentCompanyName": "Reddin-Clancy & Co",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": self.extract_tenure(quote_price_text),
            "saleType": sale_type,
        } 

        return obj

    def _load_all_listing_cards(self, max_scrolls=30):
        last_count = 0
        stagnant_rounds = 0

        for _ in range(max_scrolls):
            cards = self.driver.find_elements(By.XPATH, "//div[contains(@class,'search-results-row')]")
            current_count = len(cards)

            if current_count > last_count:
                last_count = current_count
                stagnant_rounds = 0
            else:
                stagnant_rounds += 1

            if stagnant_rounds >= 3:
                break

            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.2)
            self.driver.execute_script("window.scrollBy(0, -400);")
            time.sleep(0.6)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.2)

    # ===================== HELPERS ===================== #

    def _first_text(self, node, xpaths):
        for xp in xpaths:
            val = self._clean(" ".join(node.xpath(xp)))
            if val:
                return val
        return ""

    def _extract_features_map(self, card):
        out = {}
        items = card.xpath(".//div[contains(@class,'property-features')][1]//li")
        for li in items:
            raw = self._clean(" ".join(li.xpath(".//text()")))
            if ":" not in raw:
                continue
            key, tail = raw.split(":", 1)
            key = key.strip().lower()
            value = self._clean(" ".join(li.xpath("./span//text()"))) or self._clean(tail)
            out[key] = value
        return out

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac\.?)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

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

        m = re.search(r'[£]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?', t)
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
        t = text.upper()
        m = re.search(FULL, t)
        return m.group() if m else ""

    def normalize_sale_type(self, text):
        t = text.lower()
        if "sold" in t:
            return ""
        if "sale" in t:
            return "For Sale"
        if "let" in t or "rent" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
