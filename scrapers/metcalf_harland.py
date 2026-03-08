import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class MetcalfHarlandScraper:
    BASE_URL = "https://mhpi.co.uk/project-type/current-sales/"
    DOMAIN = "https://mhpi.co.uk"

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
        next_url = self.BASE_URL
        seen_pages = set()

        while next_url and next_url not in seen_pages:
            seen_pages.add(next_url)
            self.driver.get(next_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//article[contains(@class,'jetpack-portfolio')]",
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)
            cards = tree.xpath("//article[contains(@class,'jetpack-portfolio')]")
            if not cards:
                break

            for card in cards:
                href = self._clean("".join(
                    card.xpath(".//h2[contains(@class,'entry-title')]/a/@href")
                )) or self._clean("".join(card.xpath(".//div[contains(@class,'card-image')]//a/@href")))

                if not href:
                    continue

                listing_url = urljoin(self.DOMAIN, href)
                if listing_url in self.seen_urls:
                    continue
                self.seen_urls.add(listing_url)

                listing_summary = {
                    "title": self._clean(" ".join(card.xpath(".//h2[contains(@class,'entry-title')]//text()"))),
                    "summary_text": self._clean(" ".join(card.xpath(".//div[contains(@class,'entry-summary')]//text()"))),
                }

                try:
                    obj = self.parse_listing(listing_url, listing_summary)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

            next_href = self._clean("".join(
                tree.xpath("//nav[contains(@class,'pagination')]//a[contains(@class,'next')]/@href")
            ))
            next_url = urljoin(self.DOMAIN, next_href) if next_href else ""

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url, listing_summary):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//article[contains(@class,'section-text')]",
        )))

        tree = html.fromstring(self.driver.page_source)

        display_address = self._clean(" ".join(
            tree.xpath("//h1[contains(@class,'entry-title')]//text()")
        )) or listing_summary.get("title", "")

        bullet_text = self._clean(" ".join(
            tree.xpath("//article[contains(@class,'section-text')]//ul/li//text()")
        ))
        paragraph_text = self._clean(" ".join(
            tree.xpath("//article[contains(@class,'section-text')]//p//text()")
        ))

        detailed_description = self._clean(" ".join(
            part for part in [
                listing_summary.get("summary_text", ""),
                bullet_text,
                paragraph_text,
            ]
            if part
        ))

        sale_type = self.normalize_sale_type(" ".join([
            url,
            display_address,
            detailed_description
        ]))
        size_ft, size_ac = self.extract_size(detailed_description)
        tenure = self.extract_tenure(detailed_description)
        price = self.extract_numeric_price(detailed_description, sale_type)

        property_images = []
        for src in tree.xpath(
            "//article[contains(@class,'section-text')]//img/@src"
        ):
            full = urljoin(self.DOMAIN, src)
            if full and full not in property_images:
                property_images.append(full)

        brochure_urls = []
        for href in tree.xpath("//a[contains(translate(@href,'PDF','pdf'),'.pdf')]/@href"):
            full = urljoin(self.DOMAIN, href)
            if full not in brochure_urls:
                brochure_urls.append(full)

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Metcalf Harland",
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

        text = text.lower().replace(",", "")
        text = text.replace("ft2", "sq ft")
        text = text.replace("ft\u00b2", "sq ft")
        text = text.replace("m2", "sqm")
        text = text.replace("m\u00b2", "sqm")
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
                r"(sqm|sq\.?\s*m|square\s*metres|square\s*meters)",
                text,
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm = min(a, b) if b else a
                size_ft = round(sqm * 10.7639, 3)

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(acres?|acre|ac\.?|ha|hectares?)",
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
        if any(k in t for k in ["for sale", "current sales", "sale", "oieo", "oiro", "stc", "sstc"]):
            return "For Sale"
        if any(k in t for k in ["to let", "to rent", "rent"]):
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
