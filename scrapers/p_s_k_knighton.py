import re
from urllib.parse import urljoin, urlparse, parse_qs

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class PSKKnightonScraper:
    BASE_URL = "http://www.pskknighton.co.uk/site/go/search?sales=false"
    DOMAIN = "http://www.pskknighton.co.uk"

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

        self.wait.until(
            EC.presence_of_element_located((By.XPATH, "//div[@id='searchResults']"))
        )

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            "//div[@id='searchResults']//td[@class='thumbnail']//a/@href"
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

        self.wait.until(
            EC.presence_of_element_located((By.XPATH, "//div[@id='particularsContainer']"))
        )

        tree = html.fromstring(self.driver.page_source)

        full_text = " ".join(tree.xpath("//div[@id='particularsContainer']//text()"))

        # ---------------- ADDRESS ---------------- #
        display_address = self._clean(" ".join(
            tree.xpath("//div[@id='propertyPrice']/p[@class='center']/text()")
        ))

        # ---------------- DESCRIPTION ---------------- #
        detailed_description = self._clean(" ".join(
            tree.xpath("//h4[normalize-space()='Description']/following-sibling::p[1]//text()")
        ))

        # ---------------- SIZE ---------------- #
        size_text = " ".join(
            tree.xpath("//table[@class='featureList']//li//text()")
        )

        # fallback
        if not size_text:
            size_text = full_text

        size_ft, size_ac = self.extract_size(size_text)
        
        if not size_ft or not size_ac:
            size_ft, size_ac = self.extract_size(detailed_description)

        # ---------------- SALE TYPE ---------------- #
        sale_type = self.normalize_sale_type(full_text)

        # ---------------- PRICE ---------------- #
        price = self.extract_numeric_price(full_text, sale_type)

        # ---------------- PROPERTY TYPE ---------------- #
        property_sub_type = ""

        # Try extracting from feature text like "Retail / Cafe / E class To Let"
        if "retail" in full_text.lower():
            property_sub_type = "Retail"
        elif "office" in full_text.lower():
            property_sub_type = "Office"

        # ---------------- IMAGES ---------------- #
        property_images = []

        # main image first
        main_img = tree.xpath("//img[@id='mainPhoto']/@src")
        if main_img:
            property_images.append(urljoin(self.DOMAIN, main_img[0]))

        # thumbnails
        thumbs = tree.xpath("//div[@id='thumbs']//img/@src")
        for src in thumbs:
            full_img = src.replace("thumbnails/", "")
            property_images.append(urljoin(self.DOMAIN, full_img))

        # remove duplicates
        property_images = list(dict.fromkeys(property_images))

        # ---------------- BROCHURE ---------------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(text(),'Download PDF')]/@href")
        ]

        # ---------------- POSTCODE ---------------- #
        map_link = tree.xpath(
            "//div[@id='environmental']//a[contains(@href,'maps?q=')]/@href"
        )

        postal_code = ""
        if map_link:
            parsed = urlparse(map_link[0])
            qs = parse_qs(parsed.query)
            if "q" in qs:
                postal_code = qs["q"][0]

        if not postal_code:
            postal_code = self.extract_postcode(display_address)

        # ---------------- TENURE ---------------- #
        tenure = self.extract_tenure(full_text + " " + detailed_description)

        # ---------------- AGENT DETAILS ---------------- #
        agent_email = ""

        email_href = tree.xpath("//a[starts-with(@href,'mailto:')]/@href")
        if email_href:
            agent_email = email_href[0].replace("mailto:", "").strip()

        agent_phone = self._clean(" ".join(
            tree.xpath(
                "//h4[normalize-space()='Additional Information']"
                "/following-sibling::p//strong/text()"
            )
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
            "postalCode": postal_code,
            "brochureUrl": brochure_urls,
            "agentCompanyName": "PSK Knighton",
            "agentName": "",
            "agentCity": "",
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
        text = text.replace("ft²", "sq ft")
        text = text.replace("m²", "sqm")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        # SQUARE FEET
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*feet)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        # SQUARE METRES
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

        # ACRES
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac\.?)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        # HECTARES
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