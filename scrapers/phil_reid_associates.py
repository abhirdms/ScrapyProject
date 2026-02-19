import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class PhilReidAssociatesScraper:
    BASE_URL = "https://www.philreidassociates.com/index.php/property-listings/"
    DOMAIN = "https://www.philreidassociates.com/"

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
            "//a[contains(@class,'av-masonry-entry')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            "//a[contains(@class,'av-masonry-entry')]/@href"
        )

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

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//section[contains(@class,'av_textblock_section')]//h3"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath(
                "(//section[contains(@class,'av_textblock_section')]"
                "//div[@class='avia_textblock' and @itemprop='text']//h3)"
                "[1]/strong[last()]/text()"
            )
        ))

        # Case 2: Address as plain <h3> text (fallback)
        if not display_address:
            display_address = self._clean(" ".join(
                tree.xpath(
                    "(//section[contains(@class,'av_textblock_section')]"
                    "//div[@class='avia_textblock' and @itemprop='text']//h3)"
                    "[1]//text()"
                )
            ))

        # ---------- DESCRIPTION (SECTION ONLY) ---------- #
        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//section[contains(@class,'av_textblock_section')]"
                "//div[@class='avia_textblock' and @itemprop='text']//text()"
            )
        ))

        # ---------- SALE TYPE (TABLE → DESCRIPTION FALLBACK) ---------- #
        sale_type_raw = self._clean(" ".join(
            tree.xpath(
                "//table[@id='gvSaleTypes']"
                "//tr[td]//td[2]//text()"
            )
        ))

        if not sale_type_raw:
            sale_type_raw = self._clean(" ".join(
                tree.xpath(
                    "//section[contains(@class,'av_textblock_section')]"
                    "//div[@class='avia_textblock']//p/strong/text()"
                )
            ))

        sale_type = self.normalize_sale_type(sale_type_raw)

        if not sale_type:
            sale_type = self.normalize_sale_type(detailed_description)


        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type = self._clean(" ".join(
            tree.xpath("//span[@id='lblPropertyType']/text()")
        ))

        # ---------- SIZE (FROM DESCRIPTION ONLY) ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- TENURE (FROM DESCRIPTION ONLY) ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- PRICE (ONLY IF FOR SALE) ---------- #
        price = self.extract_numeric_price(detailed_description, sale_type)

        # ---------- IMAGES ---------- #
        property_images = [
            urljoin(self.DOMAIN, img)
            for img in tree.xpath(
                "//div[contains(@class,'avia-image-container')]"
                "//img[contains(@class,'avia_image')]/@src"
                " | "
                "//div[contains(@class,'avia-gallery')]//a[@data-rel]/@href"
            )
        ]

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@class,'av-download-btn')]/@href")
        ]

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
            "agentCompanyName": "Phil Reid Associates",
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

    def normalize_sale_type(self, text):
        if not text:
            return ""

        t = text.lower()

        if "for sale" in t or 'sale' in t:
            return "For Sale"

        if "to let" in t or "rent" in t:
            return "To Let"

        return ""


    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower()
        text = text.replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        sqft_matches = re.findall(
            r'(\d+(?:\.\d+)?)\s*(sq\.?\s*ft|sqft|sf)',
            text
        )
        if sqft_matches:
            values = [float(m[0]) for m in sqft_matches]
            size_ft = round(min(values), 3)

        acre_matches = re.findall(
            r'(\d+(?:\.\d+)?)\s*(acres?|acre|ac)',
            text
        )
        if acre_matches:
            values = [float(m[0]) for m in acre_matches]
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

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        t = text.upper()
        m = re.search(FULL, t) or re.search(PARTIAL, t)
        return m.group() if m else ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
