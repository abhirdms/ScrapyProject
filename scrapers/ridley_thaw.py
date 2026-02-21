import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class RidleyThawScraper:
    BASE_URL = "https://www.ridleythaw.co.uk/property-search/"
    DOMAIN = "https://www.ridleythaw.co.uk"

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
            "//div[@class='row']/div[contains(@class,'col-md-6')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        cards = tree.xpath("//div[@class='row']/div[contains(@class,'col-md-6')]")

        for card in cards:
            href = card.xpath(".//a/@href")
            if not href:
                continue

            url = urljoin(self.DOMAIN, href[0])
            listing_status = self._clean(" ".join(
                card.xpath(".//button[contains(@class,'sale-status')]//text()")
            ))
            listing_status_lower = listing_status.lower()
            if "sold" in listing_status_lower or "withdrawn" in listing_status_lower:
                continue
            sale_type_hint = self.normalize_sale_type(listing_status)

            if url in self.seen_urls:
                continue
            self.seen_urls.add(url)

            try:
                obj = self.parse_listing(url, sale_type_hint)
                if obj:
                    self.results.append(obj)
            except Exception:
                continue

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url, sale_type_hint=""):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'summary')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'summary')]"
                "//span[contains(@class,'span-title')]/text()"
            )
        )).rstrip(":")

        # ---------- DESCRIPTION ---------- #

        summary_text = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'summary')]"
                "//div[contains(@class,'property-inner-text')]//p//text()"
            )
        ))

        # ---------- ACCOMMODATION DETAILS ---------- #
        accommodation_text = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'accommodation')]"
                "//div[contains(@class,'property-inner-text')]//text()"
            )
        ))

        # ---------- MERGED DESCRIPTION ---------- #
        detailed_description = " ".join(
            part for part in [summary_text, accommodation_text] if part
        )


        # ---------- SALE TYPE (PRIMARY: LIST PAGE STATUS, FALLBACK: DESCRIPTION) ---------- #
        sale_type = sale_type_hint or self.normalize_sale_type(detailed_description)

        # ---------- PROPERTY SUB TYPE (KEYWORD DRIVEN) ---------- #
        property_sub_type = ""
        lower_desc = detailed_description.lower()
        if "office" in lower_desc:
            property_sub_type = "Office"
        elif "industrial" in lower_desc:
            property_sub_type = "Industrial"
        elif "retail" in lower_desc:
            property_sub_type = "Retail"
        elif "investment" in lower_desc:
            property_sub_type = "Investment"

        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(detailed_description, sale_type)

        # ---------- IMAGES ---------- #
        property_images = [
            urljoin(self.DOMAIN, src)
            for src in tree.xpath("//img[contains(@class,'img-fix')]/@src")
            if src
        ]

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath(
                "//div[contains(@class,'brochure-download')]//a/@href"
            )
            if href
        ]


        # ---------- AGENT PHONE ---------- #
        viewing_text = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'viewing')]//p//text()"
            )
        ))
        phone_match = re.search(r'0\d{3,4}\s?\d{3}\s?\d{3,4}', viewing_text)
        agent_phone = phone_match.group() if phone_match else ""

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
            "agentCompanyName": "Ridley Thaw",
            "agentName": "",
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
                size_ft = round(sqm_value * 10.7639, 3)

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

        if any(k in t for k in ["sale", "under offer"]):
            return "For Sale"
        if any(k in t for k in ["to let", "rent"]):
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
