import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class LunsonMitchenallScraper:
    BASE_URL = "https://lmrealestate.co.uk/leasing-opportunities/"
    DOMAIN = "https://lmrealestate.co.uk"

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
            "//a[contains(@class,'cr-property-link')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath("//a[contains(@class,'cr-property-link')]/@href")

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
            "//div[contains(@class,'et_pb_text_inner')]/h1"
        )))

        tree = html.fromstring(self.driver.page_source)

        title = self._clean(" ".join(tree.xpath("//div[contains(@class,'et_pb_text_inner')]/h1/text()")))
        city = self._clean(" ".join(tree.xpath("//div[contains(@class,'et_pb_text_inner')]/h2/text()")))
        display_address = self._clean(f"{title}, {city}" if city else title)

        detailed_description = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'cr-detail-description')]//p//text()")
        ))

        feature_text = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'cr-feature')]//text()[not(self::h3)]")
        ))

        availability_text = self._clean(" ".join(
            tree.xpath("//table[contains(@class,'cr-availability')]//text()")
        ))

        combined_text = " ".join(part for part in [
            detailed_description,
            feature_text,
            availability_text,
        ] if part)

        property_sub_type = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'cr-feature')][.//h3[normalize-space()='Use Class']]"
                "//p//text()"
            )
        ))

        sale_type = self.normalize_sale_type(combined_text)
        size_ft, size_ac = self.extract_size(combined_text)
        tenure = self.extract_tenure(combined_text)
        price = self.extract_numeric_price(combined_text, sale_type)

        property_images = [
            urljoin(self.DOMAIN, src)
            for src in tree.xpath("//div[contains(@class,'cr-gallery')]//img/@src")
            if src
        ]

        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//div[contains(@class,'cr-dl')]//a/@href")
            if href
        ]

        agent_name = self._clean(" ".join(
            tree.xpath("(//div[contains(@class,'cr-agent-details')]//strong/text())[1]")
        ))
        agent_email = self._clean(" ".join(
            tree.xpath("(//div[contains(@class,'cr-agent-details')]//a[starts-with(@href,'mailto:')]/text())[1]")
        ))
        agent_phone = self._clean(" ".join(
            tree.xpath("(//div[contains(@class,'cr-agent-details')]//a[starts-with(@href,'tel:')]/text())[1]")
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
            "agentCompanyName": "Lunson Mitchenall",
            "agentName": agent_name,
            "agentCity": city,
            "agentEmail": agent_email,
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
        text = re.sub(r"[\u2013\u2014\u2212]", "-", text)

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
                r"(sqm|sq\.?\s*m|m2|square\s*metres|square\s*meters)",
                text,
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm_value = min(a, b) if b else a
                size_ft = round(sqm_value * 10.7639, 3)

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(acres?|acre|ac\.?)",
            text,
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        if not size_ac:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
                r"(hectares?|ha)",
                text,
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
            "per month", "pw", "per week", "rent", "to let"
        ]):
            return ""

        m = re.search(r'[\u00a3\u20ac]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?', t)
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

        full_pattern = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b"
        partial_pattern = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\b"

        match = re.search(full_pattern, text)
        if match:
            return match.group().strip()

        match = re.search(partial_pattern, text)
        return match.group().strip() if match else ""

    def normalize_sale_type(self, text):
        t = text.lower()
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t or "under offer" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
