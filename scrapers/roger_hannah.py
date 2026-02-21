import re
import time
from urllib.parse import urljoin

from lxml import html
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class RogerHannahScraper:
    BASE_URL = "https://roger-hannah.co.uk/property-search/"
    DOMAIN = "https://roger-hannah.co.uk"

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

    def run(self):
        self.driver.get(self.BASE_URL)

        try:
            self.wait.until(EC.presence_of_element_located((
                By.XPATH,
                "//div[contains(@class,'property_card_ajax')]",
            )))
        except Exception:
            self.driver.quit()
            return self.results

        self._load_all_cards()

        tree = html.fromstring(self.driver.page_source)
        cards = tree.xpath("//div[contains(@class,'property_card_ajax')]")

        for card in cards:
            href = self._clean(" ".join(card.xpath(".//h5/a/@href")))
            if not href:
                continue

            listing_url = self.normalize_url(href)
            if listing_url in self.seen_urls:
                continue
            self.seen_urls.add(listing_url)

            listing_sub_type = self._clean(" ".join(
                card.xpath(".//div[contains(@class,'pt-7')]//ul[1]/li[1]//text()")
            ))
            listing_size = self._clean(" ".join(
                card.xpath(".//div[contains(@class,'pt-7')]//ul[1]/li[last()]//text()")
            ))
            listing_address = self._clean(" ".join(
                card.xpath(".//div[contains(@class,'pt-7')]/p[1]//text()")
            ))

            sale_labels = [
                self._clean(v)
                for v in card.xpath(".//div[contains(@class,'pt-7')]//ul[contains(@class,'font-aeonik')]//p/text()")
                if self._clean(v)
            ]
            listing_sale_text = " | ".join(sale_labels)

            listing_for_sale_price = self._clean(" ".join(
                card.xpath(
                    ".//div[contains(@class,'pt-7')]"
                    "//ul[contains(@class,'font-aeonik')]"
                    "//li[p[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'for sale')]]"
                    "//h5[1]//text()"
                )
            ))

            listing_images = self._unique([
                self.normalize_url(src)
                for src in card.xpath(".//div[contains(@class,'property-slider')]//img/@src")
                if src
            ])

            try:
                obj = self.parse_listing(
                    url=listing_url,
                    listing_sub_type=listing_sub_type,
                    listing_size=listing_size,
                    listing_address=listing_address,
                    listing_sale_text=listing_sale_text,
                    listing_for_sale_price=listing_for_sale_price,
                    listing_images=listing_images,
                )
                if obj:
                    self.results.append(obj)
            except Exception:
                continue

        self.driver.quit()
        return self.results

    def parse_listing(
        self,
        url,
        listing_sub_type="",
        listing_size="",
        listing_address="",
        listing_sale_text="",
        listing_for_sale_price="",
        listing_images=None,
    ):
        listing_images = listing_images or []

        self.driver.get(url)

        try:
            self.wait.until(EC.presence_of_element_located((By.XPATH, "//main")))
        except Exception:
            return None

        tree = html.fromstring(self.driver.page_source)

        page_title = self._clean(" ".join(tree.xpath("//h1[1]//text()")))
        detail_address = self._clean(" ".join(tree.xpath("//h2[1]//text()")))

        display_address = detail_address or listing_address or page_title

        property_sub_type = self._clean(" ".join(tree.xpath("//h6[1]//text()"))) or listing_sub_type

        detail_size = self._clean(" ".join(
            tree.xpath(
                "//p[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'size')]"
                "/following-sibling::*[1]//text()"
            )
        ))

        detail_sale_text = " | ".join([
            self._clean(v)
            for v in tree.xpath(
                "//div[contains(@class,'mt-8') and contains(@class,'w-full')]"
                "//p/text()"
            )
            if self._clean(v)
        ])

        overview_text = self._clean(" ".join(
            tree.xpath(
                "//h3[normalize-space()='Overview']"
                "/following::div[contains(@class,'location_information')][1]//text()"
            )
        ))
        location_text = self._clean(" ".join(
            tree.xpath(
                "//h3[normalize-space()='Location']"
                "/following::div[contains(@class,'location_information')][1]//text()"
            )
        ))

        key_feature_nodes = tree.xpath(
            "//h3[contains(normalize-space(), 'Key features')]/following::ul[1]/li"
        )
        key_features = self._unique([
            self._clean(" ".join(node.xpath(".//text()")))
            for node in key_feature_nodes
            if self._clean(" ".join(node.xpath(".//text()")))
        ])

        detailed_description = self._clean(" ".join(
            part
            for part in [
                page_title,
                display_address,
                " ; ".join(key_features),
                overview_text,
                location_text,
            ]
            if part
        ))

        sale_type = (
            self.normalize_sale_type(listing_sale_text)
            or self.normalize_sale_type(detail_sale_text)
            or self.normalize_sale_type(detailed_description)
        )

        sale_price_text = listing_for_sale_price or self._clean(" ".join(
            tree.xpath(
                "//p[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'for sale')]"
                "/following-sibling::*[1]//text()"
            )
        ))

        price = self.extract_numeric_price(sale_price_text or detailed_description, sale_type)

        size_ft, size_ac = self.extract_size(" ".join([listing_size, detail_size, detailed_description]))
        tenure = self.extract_tenure(detailed_description)

        detail_images = [
            self.normalize_url(src)
            for src in tree.xpath("//div[contains(@class,'slider-for')]//img/@src")
            if src
        ]

        property_images = self._unique(listing_images + detail_images)

        brochure_urls = self._unique([
            self.normalize_url(href)
            for href in tree.xpath(
                "//a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'download brochure')]/@href"
                " | //a[contains(translate(@href, 'PDF', 'pdf'), '.pdf')]/@href"
            )
            if href
        ])

        agent_name = self._clean(" ".join(
            tree.xpath("//div[@id='first']//h3[contains(@class,'teambox')]//text()")
        ))
        agent_email = self._clean(" ".join(
            tree.xpath("//div[@id='first']//a[starts-with(@href, 'mailto:')]/text()")
        ))
        agent_phone = self._clean(" ".join(
            tree.xpath("//div[@id='first']//a[starts-with(@href, 'tel:')]/text()")
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
            "agentCompanyName": "Roger Hannah",
            "agentName": agent_name,
            "agentCity": "",
            "agentEmail": agent_email,
            "agentPhone": agent_phone,
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }
        print("*****"*10)
        print(obj)
        print("*****"*10)

        return obj

    def _load_all_cards(self):
        attempts = 0

        while attempts < 40:
            current_count = len(self.driver.find_elements(By.XPATH, "//div[contains(@class,'property_card_ajax')]"))

            load_more_buttons = self.driver.find_elements(By.XPATH, "//button[@id='load-more']")
            if not load_more_buttons:
                break

            button = load_more_buttons[0]
            if not button.is_displayed() or not button.is_enabled():
                break

            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", button)
            time.sleep(0.5)
            self.driver.execute_script("arguments[0].click();", button)

            try:
                self.wait.until(lambda d: len(d.find_elements(By.XPATH, "//div[contains(@class,'property_card_ajax')]")) > current_count)
            except Exception:
                break

            attempts += 1

    def extract_size(self, text):
        if not text:
            return "", ""

        t = text.lower().replace(",", "")
        t = t.replace("ft²", "sq ft").replace("m²", "sqm")
        t = re.sub(r"[–—−]", "-", t)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*feet)",
            t,
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(acres?|acre|ac\.?)",
            t,
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale" or not text:
            return ""

        t = text.lower()

        if any(k in t for k in ["poa", "price on application", "upon application", "on application"]):
            return ""

        if any(k in t for k in ["per annum", "pa", "per year", "pcm", "per month", "pw", "per week", "rent"]):
            return ""

        m = re.search(r"[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?", t)
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
        if "leasehold" in t or "lease" in t:
            return "Leasehold"
        return ""

    def normalize_sale_type(self, text):
        if not text:
            return ""

        t = text.lower()

        has_sale = any(k in t for k in [
            "for sale", "sale", "offers", "guide price", "asking price", "under offer"
        ])
        has_let = any(k in t for k in [
            "to let", "for rent", "rent", "per annum", "pa", "pcm", "lease"
        ])

        if has_sale and has_let:
            return "For Sale"
        if has_sale:
            return "For Sale"
        if has_let:
            return "To Let"
        return ""

    def extract_postcode(self, text):
        if not text:
            return ""

        full = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b"
        partial = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\b"

        upper = text.upper()
        m = re.search(full, upper)
        if m:
            return m.group(0).strip()

        m = re.search(partial, upper)
        if m:
            return m.group(0).strip()

        return ""

    def normalize_url(self, url):
        if not url:
            return ""
        return url if url.startswith("http") else urljoin(self.DOMAIN, url)

    def _clean(self, s):
        return re.sub(r"\s+", " ", s or "").strip()

    def _unique(self, values):
        seen = set()
        out = []

        for value in values:
            if not value:
                continue
            if value in seen:
                continue
            seen.add(value)
            out.append(value)

        return out
