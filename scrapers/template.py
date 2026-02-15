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

    # ---- UPDATED SQ FT REGEX (supports sq. ft.) ----
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

    # Remove rent-based segments
    rent_keywords = [
        "per annum", "pa", "pcm",
        "per calendar month", "per sq ft", "psf"
    ]
    for word in rent_keywords:
        raw = re.sub(rf"£?\s*\d+(?:\.\d+)?\s*{word}", "", raw)

    # Standard £ prices (avoid small psf values)
    for val in re.findall(r"£\s*(\d{5,})", raw):
        prices.append(float(val))

    # Million format
    million_matches = re.findall(
        r"(?:£\s*)?(\d+(?:\.\d+)?)\s*(million|m)\b",
        raw
    )
    for num, _ in million_matches:
        prices.append(float(num) * 1_000_000)

    if prices:
        price = min(prices)
        return str(int(price)) if price.is_integer() else str(price)

    # If no numeric price found and POA wording exists
    if any(x in raw for x in [
        "poa",
        "price on application",
        "upon application",
        "on application"
    ]):
        return ""

    return ""





###################################### template code ########################



import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class HeaneyMicklethwaiteScraper:
    BASE_URL = "https://www.heaneymicklethwaite.co.uk/all_properties/"
    DOMAIN = "https://www.heaneymicklethwaite.co.uk"

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
        page = 1

        while True:
            page_url = self.BASE_URL if page == 1 else f"{self.BASE_URL}page/{page}/"
            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//article[contains(@class,'elementor-post')]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            # ✅ FIXED: ONLY elementor-cta links
            listing_urls = tree.xpath(
                "//article[contains(@class,'elementor-post')]"
                "//a[contains(@class,'elementor-cta')]/@href"
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
            "//h2[contains(@class,'elementor-heading-title')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath(
                "//section[contains(@class,'elementor-inner-section')]"
                "//div[@data-widget_type='heading.default']"
                "//h2[contains(@class,'elementor-heading-title')]/text()"
            )
        ))



        # ---------- SALE TYPE (HELPER-DRIVEN) ---------- #
        sale_type_raw = self._clean(" ".join(
            tree.xpath(
                "//h5[contains(translate(text(),"
                "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'offer')]"
                "/following::h3[1]/a/text()"
            )
        )) or display_address

        sale_type = self.normalize_sale_type(sale_type_raw)

        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type = self._clean(" ".join(
            tree.xpath(
                "//h5[normalize-space()='PROPERTRY TYPE']"
                "/following::h3[1]/a/text()"
            )
        ))

        general_info = self.get_section_text(tree, "General Information")
        location_details = self.get_section_text(tree, "Location Details")
        accommodation_details = self.get_section_text(tree, "Accomodation Details")
        rent_details = self.get_section_text(tree, "Rent Details")
        lease_terms = self.get_section_text(tree, "Lease/Rent Terms")

        detailed_description = " ".join(
            part for part in [
                general_info,
                location_details,
                accommodation_details,
                rent_details,
                lease_terms
            ] if part
        )

        detailed_description = " ".join(
            part for part in [
                general_info,
                location_details,
                accommodation_details
            ] if part
        )

        # ---------- SIZE (FROM DESCRIPTION ONLY) ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- TENURE (FROM DESCRIPTION ONLY) ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- PRICE (ONLY IF FOR SALE) ---------- #
        price = self.extract_numeric_price(detailed_description, sale_type)

        # ---------- IMAGES ---------- #
        property_images = [
            src for src in tree.xpath(
                "//div[contains(@class,'elementor-widget-image')]"
                "//img/@data-lazy-src"
            ) if src
        ]

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
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
            "agentCompanyName": "Heaney Micklethwaite",
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

    def get_section_text(self,tree, heading):
        return self._clean(" ".join(
            tree.xpath(
                f"//h3[normalize-space()='{heading}']"
                "/ancestor::div[contains(@class,'elementor-widget')]"
                "/following-sibling::div[contains(@class,'elementor-widget-text-editor')][1]"
                "//p//text()"
            )
        ))

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\s*ft|sqft|sf)', text)
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac)', text)
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
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
