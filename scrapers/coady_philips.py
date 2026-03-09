import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class CoadyPhilipsScraper:
    BASE_URL = "https://propertysearch.coadyphillips.co.uk/"
    DOMAIN = "https://propertysearch.coadyphillips.co.uk"

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
            By.XPATH, "//a[contains(@class,'property_img')]"
        )))

        tree = html.fromstring(self.driver.page_source)
        listing_urls = tree.xpath("//a[contains(@class,'property_img')]/@href")

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

    # ===================== DETAIL PAGE ===================== #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH, "//div[contains(@class,'info-details')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- TITLE ----------
        title = self._clean(" ".join(
            tree.xpath("//h2[contains(@class,'details-name')]/text()")
        ))

        # ---------- STATUS ----------
        status = self._clean(" ".join(
            tree.xpath("//h2[contains(@class,'details-name')]//span/text()")
        ))
        sale_type = self.normalize_sale_type(status)

        # ---------- ADDRESS ----------
        address = self._clean(" ".join(
            tree.xpath("//span[contains(@class,'details-address')]/text()")
        ))
        display_address = self._clean(f"{title}, {address}")

        # ---------- PRICE ----------
        price_text = self._clean(" ".join(
            tree.xpath("//a[contains(@class,'btn-third')]/text()[1]")
        ))
        price = self.extract_numeric_price(price_text, sale_type)

        # ---------- PROPERTY TYPE ----------
        property_sub_type = self._clean(" ".join(
            tree.xpath("//span[text()='Type']/following-sibling::span/strong/text()")
        ))

        # ---------- DESCRIPTION ----------
        detailed_description = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'description-text')]//text()")
        ))

        # ---------- SIZE ----------
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- TENURE ----------
        tenure = self.extract_tenure(detailed_description)

        # ---------- POSTCODE ----------
        postcode = self.extract_postcode(display_address)

        # ---------- IMAGES ----------
        property_images = list(set(
            src.strip()
            for src in tree.xpath(
                "//div[contains(@class,'fotorama')]//img[contains(@class,'fotorama__img')]/@src"
            )
            if "/large/" in src
        ))

        # ---------- BROCHURE ----------
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
            "postalCode": postcode,
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Coady Phillips",
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

    # ===================== ALLOWED HELPERS (UNCHANGED) ===================== #

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

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac\.?)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

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

        if any(k in t for k in ["poa","price on application","upon application","on application"]):
            return ""

        if any(k in t for k in ["per annum","pa","per year","pcm","per month","pw","per week","rent"]):
            return ""

        m = re.search(r"(?:\u00a3|\u00c2\u00a3|\u20ac|\u00e2\u201a\u00ac)\s*(\d+(?:,\d{3})*(?:\.\d+)?)(\s*[mk])?", t)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))
        suffix = (m.group(2) or "").strip().lower()
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

    def normalize_sale_type(self, text):
        t = text.lower()
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""


if __name__ == "__main__":
    scraper = CoadyPhilipsScraper()
    data = scraper.run()