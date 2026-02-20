import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class PhilipMarshCollinsDeungScraper:
    BASE_URL = "https://www.pmcd.co.uk/property-search/"
    DOMAIN = "https://www.pmcd.co.uk"

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
            self.driver.get(self.BASE_URL)

            # Inject POST manually (WP expects post_type=pmcdproperty)
            self.driver.execute_script("""
                var form = document.createElement('form');
                form.method = 'POST';
                form.action = arguments[0];

                var input = document.createElement('input');
                input.type = 'hidden';
                input.name = 'post_type';
                input.value = 'pmcdproperty';

                form.appendChild(input);
                document.body.appendChild(form);
                form.submit();
            """, self.BASE_URL)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//article[contains(@class,'property')]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            listing_urls = tree.xpath(
                "//article[contains(@class,'property')]//h3/a/@href"
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

            # Pagination (if exists)
            next_btn = tree.xpath(
                "//a[contains(@class,'next')]/@href"
            )

            if not next_btn:
                break

            page += 1

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h1[@class='entry-title']"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #

        # 1️⃣ Try hidden full address first
        full_address = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'brookly-hatom-data')]"
                "//span[@class='entry-title']/text()"
            )
        ))

        if full_address:
            display_address = full_address
        else:
            # 2️⃣ Fallback to h1 + h2
            title = self._clean(" ".join(
                tree.xpath("//h1[@class='entry-title']/text()")
            ))

            subtitle = self._clean(" ".join(
                tree.xpath("//h2[@class='entry-subtitle']/text()")
            ))

            display_address = self._clean(f"{title}, {subtitle}")

        subtitle = self._clean(" ".join(
            tree.xpath("//h2[@class='entry-subtitle']/text()")
        ))

        # ---------- DESCRIPTION ---------- #
        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'entry-content')]//p"
                "[not(ancestor::div[contains(@class,'brookly-hatom-data')])]//text()"
            )
        ))

        # ---------- PROPERTY DETAILS ---------- #
        property_details_text = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'property-details')]//p//text()")
        ))

        combined_text = detailed_description + " " + property_details_text

        # ---------- PROPERTY TYPE ---------- #

        property_sub_type = ""

        m = re.search(
            r'Type:\s*(.*?)\s*(?:Tenure:|$)',
            property_details_text,
            flags=re.IGNORECASE
        )

        if m:
            property_sub_type = m.group(1).strip()

        # ---------- SALE TYPE ---------- #
        sale_type = self.normalize_sale_type(combined_text)

        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(combined_text)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(combined_text)

        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(combined_text, sale_type)

        # ---------- IMAGES ---------- #
        property_images = [
            urljoin(self.DOMAIN, src)
            for src in tree.xpath(
                "//div[@class='entry-thumbnail']//img/@src"
            )
        ]

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath(
                "//div[contains(@class,'entry-brochure')]//a/@href"
            )
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
            "postalCode": self.extract_postcode(subtitle),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Philip Marsh Collins Deung",
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
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf|square\s*feet)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        if not size_ft:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(sqm|m2|square\s*metres)',
                text
            )
            if m:
                sqm = float(m.group(1))
                size_ft = round(sqm * 10.7639, 3)

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac)',
            text
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
            "poa", "price on application", "upon application"
        ]):
            return ""

        if any(k in t for k in [
            "per annum", "pa", "per month", "pcm", "rent"
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
