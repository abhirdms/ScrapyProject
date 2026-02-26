import re
import requests
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from lxml import html


class DurlingsScraper:
    BASE_URLS = [
        "https://www.durlings.co.uk/property/search/for-sale",
        "https://www.durlings.co.uk/property/search/to-let",
    ]

    DOMAIN = "https://www.durlings.co.uk"

    def __init__(self):
        self.results = []
        self.seen_urls = set()

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")

        service = Service("/usr/bin/chromedriver")
        self.driver = webdriver.Chrome(service=service, options=chrome_options)

    # ===================== RUN ===================== #

    def run(self):

        for base_url in self.BASE_URLS:

            sale_type = "For Sale" if "for-sale" in base_url else "To Let"

            page = 1

            while True:

                page_url = base_url if page == 1 else f"{base_url}?page={page}"

                self.driver.get(page_url)
                tree = html.fromstring(self.driver.page_source)

                listing_urls = tree.xpath(
                    "//div[contains(@class,'property-wrapper')]"
                    "//a[contains(@class,'property-card')]/@href"
                )

                if not listing_urls:
                    break

                new_count = 0

                for href in listing_urls:
                    url = urljoin(self.DOMAIN, href)

                    if url in self.seen_urls:
                        continue

                    self.seen_urls.add(url)
                    new_count += 1

                    try:
                        obj = self.parse_listing(url, sale_type)
                        if obj:
                            self.results.append(obj)
                    except Exception:
                        continue

                if new_count == 0:
                    break

                page += 1

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url, sale_type):

        # 🚀 FAST: use requests instead of Selenium
        response = requests.get(url, timeout=10)
        tree = html.fromstring(response.text)

        address_main = self._clean(" ".join(
            tree.xpath("//section[contains(@class,'property-address')]//h1/text()")
        ))

        postcode = self._clean(" ".join(
            tree.xpath("//section[contains(@class,'property-address')]//h1/span/text()")
        ))

        display_address = f"{address_main}, {postcode}".strip(", ")

        details_block_text = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'property-details-box')]"
                "//div[contains(@class,'details-items')]//text()"
            )
        ))

        property_sub_type = self._clean(" ".join(
            tree.xpath("//p[contains(@class,'details-item')]//span/text()")
        ))

        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//h2[normalize-space()='Description']"
                "/following-sibling::p[1]//text()"
            )
        ))

        size_ft, size_ac = self.extract_size(
            detailed_description + " " + details_block_text
        )

        tenure = self.extract_tenure(
            details_block_text + " " + detailed_description
        )

        price = self.extract_numeric_price(
            details_block_text, sale_type
        )

        property_images = tree.xpath(
            "//div[contains(@class,'property-images-slider')]"
            "//div[contains(@class,'swiper-slide')]//img/@src"
        )

        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//div[@id='docs']//a/@href")
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
            "agentCompanyName": "Durlings",
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
        if "leasehold" in t :
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
