import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class DunsterMortonScraper:

    DOMAIN = "https://www.simmonsandsons.com"

    SEARCH_URLS = [
        # Residential – For Sale
        "https://www.simmonsandsons.com/search?category=1&listingtype=5&statusids=1&obd=Descending",

        # Rural
        "https://www.simmonsandsons.com/search?tags=rural&obc=Price&obd=Descending&category=2",

        # Commercial
        "https://www.simmonsandsons.com/Search?listingType=6&dbsids=&minimumArea=&statusids=1&obc=price&obd=Descending&category=2&tags=commercial",

        # Residential – To Let
        "https://www.simmonsandsons.com/Search?listingType=6&officeids=&dbsids=&bedrooms=&minprice=&maxprice=&statusids=1&obc=price&obd=Descending"
    ]

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

        for base_url in self.SEARCH_URLS:

            page = 1

            while True:
                page_url = base_url if page == 1 else f"{base_url}&page={page}"
                self.driver.get(page_url)

                try:
                    self.wait.until(EC.presence_of_element_located((
                        By.XPATH,
                        "//div[contains(@class,'propertyListContainer')]"
                    )))
                except Exception:
                    break

                tree = html.fromstring(self.driver.page_source)

                listing_urls = tree.xpath(
                    "//div[contains(@class,'propertyListContainer')]"
                    "//figure//a/@href"
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
            "//div[@class='galleryTopWrapper']//h1"
        )))

        tree = html.fromstring(self.driver.page_source)

        display_address = self._clean(" ".join(
            tree.xpath("//div[@class='galleryTopWrapper']//h1/text()")
        ))

        price_block = self._clean(" ".join(
            tree.xpath("//div[@class='galleryTopWrapper']//h2//text()")
        ))

        description = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'fDRightCol')]"
                "//div[contains(@class,'fDDetail')]//text()"
            )
        ))

        features_text = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'featuredFDWrapper')]//li/span/text()"
            )
        ))

        detailed_description = " ".join(
            part for part in [description, features_text] if part
        )

        # ---------- PROPERTY TYPE (URL-BASED) ---------- #
        property_sub_type = self.detect_property_type(url)

        # ---------- SALE TYPE (URL FIRST → TEXT FALLBACK) ---------- #
        sale_type = self.detect_sale_type(url, price_block + " " + detailed_description)

        size_ft, size_ac = self.extract_size(detailed_description)

        tenure = self.extract_tenure(price_block + " " + detailed_description)

        price = self.extract_numeric_price(price_block, sale_type)

        property_images = [
            src for src in tree.xpath(
                "//div[@id='property-photos-device1']//img/@src"
            ) if src
        ]

        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
        ]

        agent_city = tree.xpath(
            "normalize-space(//div[contains(@class,'officeNameFD')]/span[1]/text())"
        )

        agent_phone = tree.xpath(
            "normalize-space(//a[contains(@href,'tel:')]/text())"
        )

        if not agent_phone:
            tel_href = tree.xpath(
                "normalize-space(//a[contains(@href,'tel:')]/@href)"
            )
            if tel_href:
                agent_phone = tel_href.replace("tel:", "").strip()

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
            "agentCompanyName": "Dunster & Morton",
            "agentName": "",
            "agentCity": agent_city,
            "agentEmail": "",
            "agentPhone": agent_phone,
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }


        return obj

    # ===================== NEW HELPERS ===================== #

    def detect_property_type(self, url):
        u = url.lower()

        if "/residential/" in u:
            return "Residential"
        if "/rural/" in u:
            return "Rural"
        if "/commercial/" in u:
            return "Commercial"

        return ""

    def detect_sale_type(self, url, text):
        u = url.lower()
        t = text.lower()

        if "/for-sale/" in u:
            return "For Sale"
        if "/to-let/" in u:
            return "To Let"

        if "guide price" in t or "for sale" in t or "freehold" in t:
            return "For Sale"

        if "to let" in t or "rent" in t or "per annum" in t or "pcm" in t:
            return "To Let"

        return ""

    # ===================== YOUR EXISTING HELPERS BELOW (UNCHANGED) ===================== #

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

        m = re.search(r'[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?', text.lower())
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))
        if "m" in m.group(0):
            num *= 1_000_000

        return str(int(num))

    def extract_tenure(self, text):
        t = text.lower()
        if "freehold" in t:
            return "Freehold"
        if "leasehold" in t:
            return "Leasehold"
        return ""

    def extract_postcode(self, text: str):
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

    def _clean(self, val):
        return " ".join(val.split()) if val else ""