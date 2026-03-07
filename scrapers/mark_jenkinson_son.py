import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class MarkJenkinsonSonScraper:
    BASE_URL = "https://www.markjenkinson.co.uk/property-search?include-sold=off&page=1"
    DOMAIN = "https://www.markjenkinson.co.uk"

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
        self.wait = WebDriverWait(self.driver, 20)

    # ===================== RUN ===================== #

    def run(self):
        page = 1

        while True:
            page_url = f"https://www.markjenkinson.co.uk/property-search?include-sold=off&page={page}"
            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'h-full') and contains(@class,'mb-8')]//a[contains(@href,'/property/')][1]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            listing_blocks = tree.xpath(
                "//div[contains(@class,'h-full') and contains(@class,'mb-8')]"
                "[.//a[contains(@href,'/property/')]]"
            )

            if not listing_blocks:
                break

            added_on_page = 0

            for block in listing_blocks:
                href = self._clean(" ".join(
                    block.xpath(".//a[contains(@href,'/property/')][1]/@href")
                ))
                if not href:
                    continue

                listing_url = urljoin(self.DOMAIN, href)
                if listing_url in self.seen_urls:
                    continue

                status_text = self._extract_listing_status(block)
                if self.is_sold_or_unavailable(status_text):
                    continue

                self.seen_urls.add(listing_url)

                try:
                    obj = self.parse_listing(listing_url, status_text)
                    if obj:
                        self.results.append(obj)
                        added_on_page += 1
                except Exception:
                    continue

            if added_on_page == 0 and page > 1:
                # End when next pages only contain skipped/duplicate entries
                break

            page += 1

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url, listing_status_text=""):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h1[contains(@class,'text-primary')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        display_address = self._clean(" ".join(
            tree.xpath("//h1[contains(@class,'text-primary')]//text()")
        ))

        price_text = self._clean(" ".join(
            tree.xpath(
                "(//div[contains(@class,'data-property-actions')]"
                "//div[contains(@class,'text-3xl')])[1]//text()"
            )
        ))

        page_text = self._clean(tree.xpath("string(//body)"))

        sale_type = self.normalize_sale_type(
            " ".join([listing_status_text, price_text, page_text])
        )

        if sale_type == "Sold":
            return None

        property_sub_type = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'text-base') and contains(@class,'font-bold')][1]//text()"
            )
        ))

        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//div[@data-tab-content='details']"
                "//div[contains(@class,'cms-content')]//text()"
            )
        ))

        size_ft, size_ac = self.extract_size(detailed_description)
        tenure = self.extract_tenure(detailed_description)
        price = self.extract_numeric_price(price_text, sale_type)

        property_images = list(dict.fromkeys([
            urljoin(self.DOMAIN, src)
            for src in tree.xpath(
                "//a[@data-id='property-images']/@href | "
                "//div[contains(@class,'property-main-image')]//img/@src"
            )
            if src and src.strip()
        ]))

        brochure_urls = list(dict.fromkeys([
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
            if href and href.strip()
        ]))

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
            "agentCompanyName": "Mark Jenkinson & Son",
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

    def _extract_listing_status(self, block):
        status_text = self._clean(" ".join(
            block.xpath(
                ".//div[contains(@class,'absolute') and contains(@class,'bottom-0')]//text() | "
                ".//p[contains(@class,'text-secondary') and contains(@class,'font-bold')]//text()"
            )
        ))
        return status_text

    def is_sold_or_unavailable(self, text):
        if not text:
            return False

        t = text.lower()
        return any(k in t for k in [
            "sold",
            "sold prior",
            "sold post auction",
            "withdrawn",
        ])

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower()
        text = text.replace(",", "")
        text = text.replace("ft²", "sq ft")
        text = text.replace("m²", "sqm")
        text = re.sub(r"[–—-]", "-", text)

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
            "per month", "pw", "per week", "rent"
        ]):
            return ""

        m = re.search(r"[£]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?", text)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))
        if "m" in m.group(0).lower():
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
        t = (text or "").lower()

        if any(k in t for k in ["sold", "sold prior", "sold post auction", "withdrawn"]):
            return "Sold"

        if "to let" in t or "let" in t or "rent" in t:
            return "To Let"

        if "guide price" in t or "auction" in t or "for sale" in t or "sale" in t:
            return "For Sale"

        return "For Sale"

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
