import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class FirstCityScraper:
    BASE_URL = "https://www.firstcity.co.uk/properties"
    DOMAIN = "https://www.firstcity.co.uk"

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
        start = 0
        page_size = 20

        while True:
            page_url = self.BASE_URL if start == 0 else f"{self.BASE_URL}?start={start}"
            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//li[contains(@class,'find-property-item')]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)
            listing_urls = tree.xpath(
                "//li[contains(@class,'find-property-item')]"
                "//h4[contains(@class,'result-title')]"
                "/a[not(contains(@class,'details'))][1]/@href"
            )

            if not listing_urls:
                break

            new_urls_found = False

            for href in listing_urls:
                url = urljoin(self.DOMAIN, href)
                if url in self.seen_urls:
                    continue

                self.seen_urls.add(url)
                new_urls_found = True

                try:
                    obj = self.parse_listing(url)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

            if not new_urls_found:
                break

            start += page_size

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'property-view')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        display_address = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'page-header')]//h1/text()")
        ))

        property_sub_type = self.get_prop_detail_value(tree, "Type")
        size_text = self.get_prop_detail_value(tree, "Size")
        status_text = self.get_prop_detail_value(tree, "Status")
        location_text = self.get_prop_detail_value(tree, "Location")

        summary_points = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'prop-details')]/ul[2]//li//text()"
            )
        ))
        full_description = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'property-full-desc')]"
                "//div[contains(@class,'std')]//text()"
            )
        ))
        detailed_description = self._clean(" ".join(
            part for part in [summary_points, full_description] if part
        ))

        sale_type = self.normalize_sale_type(" ".join([status_text, detailed_description]))
        size_ft, size_ac = self.extract_size(" ".join([size_text, detailed_description]))
        tenure = self.extract_tenure(detailed_description)
        price = self.extract_numeric_price(detailed_description, sale_type)

        property_images = [
            urljoin(self.DOMAIN, src)
            for src in tree.xpath(
                "//div[contains(@class,'property-pane')]"
                "//img[contains(@class,'prop-img')]/@src"
            )
            if src
        ]
        for src in tree.xpath("//div[contains(@class,'property-full-desc')]//img/@src"):
            full = urljoin(self.DOMAIN, src)
            if full and full not in property_images:
                property_images.append(full)

        brochure_urls = []
        for href in tree.xpath("//a[contains(@href,'.pdf')]/@href"):
            full = urljoin(self.DOMAIN, href)
            if full not in brochure_urls:
                brochure_urls.append(full)


        effective_address = location_text or display_address

        obj = {
            "listingUrl": url,
            "displayAddress": display_address or effective_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(effective_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "First City",
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

    def get_prop_detail_value(self, tree, label):
        return self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'prop-details')]"
                f"//li[strong[contains(normalize-space(),'{label}:')]]"
                "/text()"
            )
        ))

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = text.replace("ft2", "sq ft")
        text = text.replace("ft²", "sq ft")
        text = text.replace("m2", "sqm")
        text = text.replace("m²", "sqm")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*feet)",
            text,
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        if not size_ft:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
                r"(sqm|sq\.?\s*m|square\s*metres|square\s*meters)",
                text,
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm = min(a, b) if b else a
                size_ft = round(sqm * 10.7639, 3)

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac|ha|hectares?)",
            text,
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            value = min(a, b) if b else a
            unit = m.group(3)
            if unit and ("ha" in unit or "hectare" in unit):
                value = value * 2.47105
            size_ac = round(value, 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if not text:
            return ""

        if sale_type and sale_type.lower() not in {"for sale", "for sale / to let"}:
            return ""

        t = text.lower()

        if any(k in t for k in ["poa", "price on application", "upon application", "on application"]):
            return ""

        if any(k in t for k in ["per annum", "pa", "per year", "pcm", "per month", "pw", "per week"]):
            return ""

        m = re.search(r"£\s*(\d+(?:,\d{3})*(?:\.\d+)?)(\s*m|\s*k)?", t)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))
        suffix = (m.group(2) or "").strip()
        if suffix == "m":
            num *= 1_000_000
        if suffix == "k":
            num *= 1_000

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

        t = text.upper()
        full_pattern = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b"
        partial_pattern = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\b"

        match = re.search(full_pattern, t)
        if match:
            return match.group().strip()

        match = re.search(partial_pattern, t)
        return match.group().strip() if match else ""



    def normalize_sale_type(self, text):
        t = (text or "").lower()

        has_sale = any(k in t for k in ["for sale", "sale", "stc", "sstc"])
        has_let = any(k in t for k in ["to let", "to rent", "let", "lease", "letting"])

        if has_sale and has_let:
            return "For Sale"
        if has_sale:
            return "For Sale"
        if has_let:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
