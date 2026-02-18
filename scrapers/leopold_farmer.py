import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class LeopoldFarmerScraper:
    BASE_URLS = [
        "https://www.leopoldfarmer.com/offices.htm",
        "https://www.leopoldfarmer.com/properties.htm",
    ]
    DOMAIN = "https://www.leopoldfarmer.com"

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
        for page_url in self.BASE_URLS:
            self.driver.get(page_url)

            self.wait.until(EC.presence_of_element_located((By.XPATH, "//a[@name]")))
            tree = html.fromstring(self.driver.page_source)

            # Remove duplicate anchors but preserve order
            anchors = list(dict.fromkeys(tree.xpath("//a[@name]/@name")))

            for anchor in anchors:
                if anchor.lower() == "top":
                    continue

                listing_url = f"{page_url}#{anchor}"

                if listing_url in self.seen_urls:
                    continue
                self.seen_urls.add(listing_url)

                try:
                    obj = self.parse_listing(tree, anchor, listing_url)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, tree, anchor, listing_url):

        # Correct container selection
        section = tree.xpath(
            f"//table[@width='650'][.//a[@name='{anchor}']][1]"
        )
        if not section:
            return None

        section = section[0]

        raw_text = self._clean(" ".join(
            section.xpath(".//text()[normalize-space()]")
        ))

        if not raw_text:
            return None

        # ---------- DISPLAY ADDRESS (HEADER ONLY) ---------- #
        header_text = self._clean(" ".join(
            section.xpath(
                ".//a[@name='%s']/following::font[1]/text()" % anchor
            )
        ))

        display_address = header_text

        display_address = display_address.rstrip("-").strip()


        # ---------- SALE TYPE ---------- #
        sale_type = self.normalize_sale_type(raw_text)

        if "Sold" == sale_type:
            return None


        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(raw_text)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(raw_text)

        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(raw_text, sale_type)

        # ---------- IMAGES (FILTERED) ---------- #
        property_images = [
            urljoin(self.DOMAIN, src)
            for src in section.xpath(".//img/@src")
            if src
            and not any(x in src.lower() for x in [
                "bullet.gif",
                "logo.gif",
                "_tn",
                "tn.jpg",
                "download",
            ])
        ]

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in section.xpath(".//a[contains(@href,'.pdf')]/@href")
        ]
        obj = {
            "listingUrl": listing_url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": property_images,
            "detailedDescription": raw_text,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Leopold Farmer",
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

        t = text.lower()

        size_ft = ""
        size_ac = ""

        # sq ft (first occurrence)
        m = re.search(r'([\d,]+)\s*sq\.?\s*ft', t)
        if m:
            size_ft = int(m.group(1).replace(",", ""))

        # acres ONLY if near "site" or "total site"
        m = re.search(r'(site|total site)[^\d]*([\d\.]+)\s*acres?', t)
        if m:
            size_ac = float(m.group(2))

        return size_ft, size_ac


    def extract_numeric_price(self, text, sale_type):
        if sale_type == "To Let":
            return ""

        if not text:
            return ""

        t = text.lower()

        if "payment of" in t:
            t = t.split("payment of")[0]

        prices = re.findall(r'£\s*([\d,]+)', t)
        if not prices:
            return ""

        values = [int(p.replace(",", "")) for p in prices]

        return str(max(values))



    def extract_tenure(self, text):
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

    def normalize_sale_type(self, text):
        t = text.lower()

        if "sold" in t:
            return "Sold"
        
   
        if "sale" in t:
            return "For Sale"

        if "to let" in t:
            return "To Let"

        return ""


    def _clean(self, val):
        return " ".join(val.split()) if val else ""
