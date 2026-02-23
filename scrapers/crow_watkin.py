import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from lxml import html


class CrowWatkinScraper:
    DOMAIN = "https://www.crowwatkin.co.uk"
    SEARCH_URLS = [
        "https://www.crowwatkin.co.uk/commercial-sales/",
        "https://www.crowwatkin.co.uk/commercial-lettings/",
    ]

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
        for base_url in self.SEARCH_URLS:
            page = 1

            while True:
                page_url = base_url if page == 1 else f"{base_url}page/{page}/"
                self.driver.get(page_url)

                try:
                    self.wait.until(EC.presence_of_element_located((
                        By.XPATH,
                        "//div[contains(@class,'wpsight-listings')]//h2/a"
                    )))
                except Exception:
                    break

                tree = html.fromstring(self.driver.page_source)
                listing_urls = tree.xpath(
                    "//div[contains(@class,'wpsight-listings')]"
                    "//h2[contains(@class,'entry-title')]/a/@href"
                )

                if not listing_urls:
                    break

                initial_count = len(self.seen_urls)

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

                if len(self.seen_urls) == initial_count:
                    break

                page += 1

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'wpsight-listing')]//h1"
        )))

        tree = html.fromstring(self.driver.page_source)

        display_address = self._clean(" ".join(
            tree.xpath("//h1[contains(@class,'entry-title')]/text()")
        ))

        raw_price = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'wpsight-listing-price')]"
                "//span[contains(@class,'listing-price-value')]/@content"
            )
        )) or self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'wpsight-listing-price')]"
                "//span[contains(@class,'listing-price-value')]/text()"
            )
        ))

        sale_type_raw = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'wpsight-listing-status')]"
                "//span[contains(@class,'badge')]/text()"
            )
        ))
        sale_type = self.normalize_sale_type(sale_type_raw)

        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'wpsight-listing-description')]//text()"
            )
        ))

        size_ft, size_ac = self.extract_size(detailed_description)
        tenure = self.extract_tenure(detailed_description)
        price = self.extract_numeric_price(raw_price, sale_type)

        property_images = list(dict.fromkeys(
            [
                src for src in (
                    tree.xpath("//meta[@itemprop='image']/@content")
                    + tree.xpath(
                        "//div[contains(@class,'wpsight-listing-thumbnail')]//img/@src"
                    )
                    + tree.xpath(
                        "//div[contains(@class,'wpsight-listing-description')]//img/@src"
                    )
                ) if src
            ]
        ))

        brochure_urls = list(dict.fromkeys([
            urljoin(self.DOMAIN, href)
            for href in tree.xpath(
                "//a[contains(@href,'.pdf') or contains(@href,'.doc') or contains(@href,'.docx')]/@href"
            )
        ]))

        agent_phone = self.extract_agent_phone(detailed_description)

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
            "agentCompanyName": "Crow Watkin",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": agent_phone,
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }

        print("*****" * 10)
        print(obj)
        print("*****" * 10)

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

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*feet)",
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        if not size_ft:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
                r"(sqm|sq\.?\s*m|m2|square\s*metres|square\s*meters)",
                text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm_value = min(a, b) if b else a
                size_ft = round(sqm_value * 10.7639, 3)

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(acres?|acre|ac\.?)",
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        if not size_ac:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
                r"(hectares?|ha)",
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

        m = re.search(r"[£€]?\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?", t)
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
        if "rent" in t or "let" in t:
            return "To Let"
        return ""

    def extract_agent_phone(self, text):
        if not text:
            return ""

        m = re.search(
            r"(?:tel|telephone|phone)\s*[:.]?\s*(\+?\d[\d\s().-]{7,}\d)",
            text,
            re.IGNORECASE,
        )
        return self._clean(m.group(1)) if m else ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
