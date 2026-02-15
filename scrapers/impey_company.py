
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class ImpeyCompanyScraperAbhi:
    BASE_URL = "https://www.impey.co.uk/property/"
    DOMAIN = "https://www.impey.co.uk"

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

        self.driver.get("https://www.impey.co.uk/available-properties/")

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//article[contains(@class,'property-result-container')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            "//article[contains(@class,'property-result-container')]//a/@href"
        )

        for url in listing_urls:
            url = urljoin(self.DOMAIN, url)

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
            "//div[contains(@class,'c-Banner_Box')]/h2"
        )))

        tree = html.fromstring(self.driver.page_source)

        display_address = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'c-Banner_Box')]/h2/text()")
        ))

        sale_type_raw = self._clean(" ".join(
            tree.xpath("//p[@id='tenure']/text()")
        ))

        sale_type = self.normalize_sale_type(sale_type_raw)

        property_sub_type = self._clean(" ".join(
            tree.xpath("//summary[@id='property_meta']/p[1]/text()")
        ))

        detailed_description = self._clean(" ".join(
            tree.xpath("//main[contains(@class,'entry-content')]/p/text()")
        ))

        size_text = self._clean(" ".join(
            tree.xpath("//p[@id='overall_size']/text()")
        ))

        size_ft, size_ac = extract_size(size_text)

        price_text = self._clean(" ".join(
            tree.xpath("//p[@id='overall_price']/text()")
        ))

        price = extract_price(price_text, sale_type)

        property_images = [
            urljoin(self.DOMAIN, src)
            for src in tree.xpath("//li//div[contains(@class,'image_group')]//img/@src")
        ]

        brochure_urls = []

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Impey & Company",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": "",
            "saleType": sale_type,
        }

        return obj

    # ===================== HELPERS ===================== #

    def normalize_sale_type(self, text):
        t = text.lower()
        if "sale" in t:
            return "For Sale"
        if "let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""


# size_extraction 

import re


def extract_size(text: str):

    if not text:
        return "", ""

    SQM_TO_SQFT = 10.7639
    HECTARE_TO_ACRE = 2.47105

    text = text.lower().replace(",", "")
    text = re.sub(r"[–—−]", "-", text)

    size_ft = ""
    size_ac = ""

    m = re.search(
        r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\.?\s*ft\.?|sqft|sf)\b',
        text
    )
    if m:
        a = float(m.group(1))
        b = float(m.group(2)) if m.group(2) else None
        size_ft = round(min(a, b), 3) if b else round(a, 3)
        return size_ft, size_ac

    m = re.search(
        r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sqm|m2|m²)\b',
        text
    )
    if m:
        a = float(m.group(1))
        b = float(m.group(2)) if m.group(2) else None
        val = min(a, b) if b else a
        size_ft = round(val * SQM_TO_SQFT, 3)
        return size_ft, size_ac

    m = re.search(
        r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac)\b',
        text
    )
    if m:
        a = float(m.group(1))
        b = float(m.group(2)) if m.group(2) else None
        size_ac = round(min(a, b), 3) if b else round(a, 3)
        return size_ft, size_ac

    m = re.search(
        r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(hectares?|hectare|ha)\b',
        text
    )
    if m:
        a = float(m.group(1))
        b = float(m.group(2)) if m.group(2) else None
        val = min(a, b) if b else a
        size_ac = round(val * HECTARE_TO_ACRE, 3)
        return size_ft, size_ac

    return size_ft, size_ac


################################## lease ###############################

def extract_tenure(text: str):
    if not text:
        return ""
    
    t = text.lower()

    if "freehold" in t:
        return "Freehold"

    if "leasehold" in t:
        return "Leasehold"

    return ""


################################# postcode

def extract_postcode(text: str):
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


#################################### price ##############################

def extract_price(text: str, sale_type: str = None):
    if not text:
        return ""

    if sale_type and sale_type.lower() != "for sale":
        return ""

    raw = (
        text.lower()
        .replace(",", "")
        .replace("\u00a0", " ")
    )

    raw = re.sub(r"(to|–|—)", "-", raw)

    prices = []

    rent_keywords = [
        "per annum", "pa", "pcm",
        "per calendar month", "per sq ft", "psf"
    ]
    for word in rent_keywords:
        raw = re.sub(rf"£?\s*\d+(?:\.\d+)?\s*{word}", "", raw)

    for val in re.findall(r"£\s*(\d{5,})", raw):
        prices.append(float(val))

    million_matches = re.findall(
        r"(?:£\s*)?(\d+(?:\.\d+)?)\s*(million|m)\b",
        raw
    )
    for num, _ in million_matches:
        prices.append(float(num) * 1_000_000)

    if prices:
        price = min(prices)
        return str(int(price)) if price.is_integer() else str(price)

    if any(x in raw for x in [
        "poa",
        "price on application",
        "upon application",
        "on application"
    ]):
        return ""

    return ""

