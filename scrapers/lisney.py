import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class LisneyScraper:

    BASE_URLS = [
        "https://lisney.com/commercial-listing/",
        "https://lisney.com/property/residential/for-sale/",
        "https://lisney.com/property/residential/to-let/",
        "https://lisney.com/property/residential/new-homes/",
        "https://lisney.com/property/residential/country-homes/",
    ]

    DOMAIN = "https://lisney.com"

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

        for base_url in self.BASE_URLS:

            page = 1

            while True:

                page_url = base_url if page == 1 else f"{base_url}?paged={page}"
                self.driver.get(page_url)

                try:
                    self.wait.until(EC.presence_of_element_located((
                        By.XPATH,
                        "//div[@id='property_listing_result']//div[contains(@class,'property_box')]"
                    )))
                except Exception:
                    break

                tree = html.fromstring(self.driver.page_source)

                cards = tree.xpath(
                    "//div[@id='property_listing_result']//div[contains(@class,'property_box')]"
                )

                if not cards:
                    break

                for card in cards:

                    display_address = self._clean(" ".join(
                        card.xpath(
                            ".//div[contains(@class,'property_title')]//a/text()"
                        )
                    ))

                    href = card.xpath(
                        ".//a[contains(@class,'blankinfo_link')]/@href"
                    )

                    if not href:
                        continue

                    url = urljoin(self.DOMAIN, href[0])

                    if url in self.seen_urls:
                        continue
                    self.seen_urls.add(url)

                    try:
                        obj = self.parse_listing(url, display_address)
                        if obj:
                            self.results.append(obj)
                    except Exception:
                        continue

                page += 1

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url, display_address):

        self.driver.get(url)

        try:
            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        except Exception:
            return None

        tree = html.fromstring(self.driver.page_source)

        # -------- DESCRIPTION (FEATURES TAB ONLY) -------- #


        description_parts = []

        # --------------------------------------------------
        # 1️⃣ COMMERCIAL LAYOUT (feature + location tabs)
        # --------------------------------------------------

        feature_paragraphs = tree.xpath(
            "//div[@id='feature-detail']//div[contains(@class,'redbox_scroller_overview') and contains(@class,'desktop')]//p//text()"
        )

        description_parts.extend(
            [self._clean(t) for t in feature_paragraphs if self._clean(t)]
        )

        feature_bullets = tree.xpath(
            "//div[@id='feature-detail']//div[contains(@class,'col-md-6')]/ul/li/text()"
        )

        description_parts.extend(
            [self._clean(t) for t in feature_bullets if self._clean(t)]
        )

        location_paragraphs = tree.xpath(
            "//div[@id='location-detail']//div[contains(@class,'redbox_scroller_location') and contains(@class,'desktop')]//p//text()"
        )

        description_parts.extend(
            [self._clean(t) for t in location_paragraphs if self._clean(t)]
        )


        # --------------------------------------------------
        # 2️⃣ RESIDENTIAL OVERVIEW SECTION
        # --------------------------------------------------

        # Icon summary
        icon_text = tree.xpath(
            "//div[contains(@class,'property_detail_list')]"
            "//div[contains(@class,'icon_col')]//text()"
        )

        description_parts.extend(
            [self._clean(t) for t in icon_text if self._clean(t)]
        )

        # Expanded overview only (avoid first-desc duplication)
        overview_text = tree.xpath(
            "//div[@id='id-res-desc']//p//text()"
        )

        description_parts.extend(
            [self._clean(t) for t in overview_text if self._clean(t)]
        )


        # --------------------------------------------------
        # 3️⃣ RESIDENTIAL PROPERTY DETAILS (Accommodation)
        # --------------------------------------------------

        accommodation_items = tree.xpath(
            "//div[contains(@class,'detail_property_section')]"
            "//ul[contains(@class,'full-details')]//li//text()"
        )

        description_parts.extend(
            [self._clean(t) for t in accommodation_items if self._clean(t)]
        )


        # --------------------------------------------------
        # 4️⃣ REMOVE DUPLICATES + CLEAN
        # --------------------------------------------------

        seen = set()
        cleaned = []

        for part in description_parts:
            if part and part not in seen:
                seen.add(part)
                cleaned.append(part)

        detailed_description = "\n".join(cleaned)






        # ---------- SALE TYPE (USING normalize_sale_type) ---------- #
        sale_type_source = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'property-status_name')]//strong/text()"
            )
        ))

        if not sale_type_source:
            sale_type_source = self._clean(" ".join(
                tree.xpath("//div[contains(@class,'property-price_qualifier')]/text()")
            ))

        if not sale_type_source:
            sale_type_source = f"{display_address} {detailed_description}"

        sale_type = self.normalize_sale_type(sale_type_source)


        # ---------- PRICE ---------- #
        price_text = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'price')]/text()")
        ))

        price = self.extract_numeric_price(price_text, sale_type)


        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- IMAGES ---------- #
        property_images = []

        styles = tree.xpath("//div[contains(@class,'pro_img')]/@style")
        for style in styles:
            m = re.search(r"url\('(.+?)'\)", style)
            if m:
                property_images.append(m.group(1))

        property_images += tree.xpath("//img/@src")

        property_images = list(set([
            urljoin(self.DOMAIN, img)
            for img in property_images
            if img and "logo" not in img.lower()
        ]))

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
        ]
        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Lisney",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
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
        text = re.sub(r"[–—−&]", "-", text)

        size_ft = ""
        size_ac = ""

        # Match sq ft (with multiple values, take minimum)
        matches = re.findall(
            r'(\d+(?:\.\d+)?)\s*(sq\.?\s*ft|sqft|sf)',
            text
        )
        if matches:
            values = [float(v[0]) for v in matches]
            size_ft = round(min(values), 3)

        # Match sqm and convert
        matches = re.findall(
            r'(\d+(?:\.\d+)?)\s*(sqm|m2|m²)',
            text
        )
        if matches:
            values = [float(v[0]) for v in matches]
            size_ft = round(min(values) * 10.7639, 3)

        # Match acres
        matches = re.findall(
            r'(\d+(?:\.\d+)?)\s*(acres?|acre|ac)',
            text
        )
        if matches:
            values = [float(v[0]) for v in matches]
            size_ac = round(min(values), 3)

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

        m = re.search(r'[€£]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?', t)
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

        # Irish Eircode pattern
        eircode_pattern = r'\b[A-Z]\d{2}\s?[A-Z0-9]{4}\b'

        match = re.search(eircode_pattern, text)
        return match.group() if match else ""


    def normalize_sale_type(self, text):
        t = text.lower()
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""


    def _clean(self, val):
        return " ".join(val.split()) if val else ""
