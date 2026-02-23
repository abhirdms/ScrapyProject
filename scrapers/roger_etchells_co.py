import re
from urllib.parse import urljoin

from lxml import html
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class RogerEtchellsCoScraper:
    BASE_URLS = [
        {
            "url": "https://www.rogeretchells.co.uk/retail",
            "property_sub_type": "Retail",
        },
        {
            "url": "https://www.rogeretchells.co.uk/offices",
            "property_sub_type": "Office",
        },
        {
            "url": "https://www.rogeretchells.co.uk/industrial",
            "property_sub_type": "Industrial",
        },
    ]

    DOMAIN = "https://www.rogeretchells.co.uk"

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

    def run(self):
        for cfg in self.BASE_URLS:
            self.driver.get(cfg["url"])

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//a[@aria-label='Download Full Details']"
                )))
            except Exception:
                continue

            tree = html.fromstring(self.driver.page_source)
            anchors = tree.xpath("//a[@aria-label='Download Full Details']")

            for anchor in anchors:
                href = self._clean(" ".join(anchor.xpath("./@href")))
                if not href:
                    continue

                url = href if href.startswith("http") else urljoin(self.DOMAIN, href)

                if url in self.seen_urls:
                    continue
                self.seen_urls.add(url)

                listing_address = self._clean(" ".join(
                    anchor.xpath(
                        "./ancestor::div[contains(@class,'FubTgk')][1]"
                        "/preceding::div[@data-testid='richTextElement'][1]//text()"
                    )
                ))

                listing_description = self._clean(" ".join(
                    anchor.xpath(
                        "./ancestor::div[contains(@class,'FubTgk')][1]"
                        "/following::div[@data-testid='richTextElement'][1]//text()"
                    )
                ))

                listing_images = [
                    src for src in anchor.xpath(
                        "./ancestor::div[contains(@class,'SPY_vo')][1]"
                        "//div[@data-testid='slide-show-gallery-items']//img/@src"
                    ) if src
                ]

                try:
                    obj = self.parse_listing(
                        url=url,
                        property_sub_type=cfg["property_sub_type"],
                        listing_address=listing_address,
                        listing_description=listing_description,
                        listing_images=listing_images,
                    )
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

        self.driver.quit()
        return self.results

    def parse_listing(
        self,
        url,
        property_sub_type,
        listing_address="",
        listing_description="",
        listing_images=None,
    ):
        listing_images = listing_images or []

        self.driver.get(url)

        try:
            self.wait.until(EC.presence_of_element_located((
                By.XPATH,
                "//body"
            )))
        except Exception:
            return None

        tree = html.fromstring(self.driver.page_source)

        display_address = listing_address or self._clean(" ".join(
            tree.xpath(
                "(//div[@data-testid='richTextElement']"
                "//*[self::h1 or self::h2 or self::h3 or self::h4]//text())[1]"
            )
        ))

        detail_description = self._clean(" ".join(
            tree.xpath("//div[@data-testid='richTextElement']//text()")
        ))

        detailed_description = self._clean(" ".join(
            part for part in [listing_description, detail_description] if part
        ))

        page_text = self._clean(" ".join(tree.xpath("//body//text()")))

        sale_type = (
            self.normalize_sale_type(listing_description)
            or self.normalize_sale_type(page_text)
        )

        price = self.extract_numeric_price(page_text, sale_type)
        size_ft, size_ac = self.extract_size(detailed_description)
        tenure = self.extract_tenure(detailed_description)

        detail_images = [
            src for src in tree.xpath(
                "//div[@data-testid='slide-show-gallery-items']//img/@src"
            ) if src
        ]

        property_images = self._unique(listing_images + detail_images)

        brochure_urls = self._unique([
            href if href.startswith("http") else urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(translate(@href, 'PDF', 'pdf'), '.pdf')]/@href")
            if href
        ])

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
            "agentCompanyName": "Roger Etchells & Co",
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
            text,
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(acres?|acre|ac\.?)",
            text,
        )
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

        m = re.search(r"[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?", t)
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

    def normalize_sale_type(self, text):
        if not text:
            return ""

        t = text.lower()

        sale_keys = [
            "for sale", "sale", "freehold", "investment for sale", "offers over",
            "guide price", "asking price", "long leasehold"
        ]
        let_keys = [
            "to let", "for rent", "rent", "rental", "lease", "per annum",
            "pa", "pcm", "per month", "licence"
        ]

        has_sale = any(k in t for k in sale_keys)
        has_let = any(k in t for k in let_keys)

        if has_sale and has_let:
            return "For Sale"
        if has_sale:
            return "For Sale"
        if has_let:
            return "To Let"
        return ""

    def extract_postcode(self, text):
        if not text:
            return ""

        full = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b"
        partial = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\b"

        m = re.search(full, text.upper())
        if m:
            return m.group(0).strip()

        m = re.search(partial, text.upper())
        if m:
            return m.group(0).strip()

        return ""

    def _clean(self, s):
        return re.sub(r"\s+", " ", s or "").strip()

    def _unique(self, values):
        seen = set()
        out = []
        for v in values:
            if not v:
                continue
            if v in seen:
                continue
            seen.add(v)
            out.append(v)
        return out
