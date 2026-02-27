import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class GalePriggenCoScraper:
    BASE_URL = "https://search.galepriggen.co.uk/properties"
    DOMAIN = "https://search.galepriggen.co.uk"

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
            page_url = f"{self.BASE_URL}?page={page}"
            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'propItem')]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            listing_urls = tree.xpath(
                "//div[contains(@class,'propItem')]"
                "//a[contains(@class,'propImg')]/@href"
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
            "//div[@class='propTitle']/h1"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//div[@class='propTitle']/p[@class='lead']/text()")
        ))

        # ---------- PROPERTY TYPE ---------- #
        property_sub_type = self._clean(" ".join(
            tree.xpath(
                "//table//tr[td[1][contains(.,'Property Type')]]/td[2]/text()"
            )
        ))

        # ---------- TENURE ---------- #
        tenure_raw = self._clean(" ".join(
            tree.xpath(
                "//table//tr[td[1][contains(.,'Tenure')]]/td[2]/text()"
            )
        ))

        tenure = self.extract_tenure(tenure_raw)

        # ---------- PRICE / RENT ---------- #
        rent_text = self._clean(" ".join(
            tree.xpath(
                "//table//tr[td[1][contains(.,'Rent')]]/td[2]/text()"
            )
        ))

        price_text = self._clean(" ".join(
            tree.xpath(
                "//table//tr[td[1][contains(.,'Price')]]/td[2]/text()"
            )
        ))

        # ---------- SALE TYPE ---------- #
        sale_type = ""
        if rent_text:
            sale_type = "To Let"
        elif price_text:
            sale_type = "For Sale"

        price = self.extract_numeric_price(price_text, sale_type)

        # ---------- DESCRIPTION ---------- #
        description = self._clean(" ".join(
            tree.xpath(
                "//h2[normalize-space()='Description']"
                "/following-sibling::p[1]//text()"
            )
        ))

        key_points = tree.xpath(
            "//h2[normalize-space()='Key Points']"
            "/following-sibling::ul[1]/li/text()"
        )

        if key_points:
            description += " Key Points: " + " ".join(
                self._clean(k) for k in key_points
            )

        # ---------- SIZE ---------- #
        size_text = self._clean(" ".join(
            tree.xpath(
                "//table//tr[td[1][contains(.,'Size')]]/td[2]/text()"
            )
        ))

        size_ft, size_ac = self.extract_size(size_text)

        # ---------- IMAGES ---------- #
        property_images = list(set(
            tree.xpath(
                "//div[contains(@class,'cycle-slideshow-thumbnails')]"
                "//img/@src"
            )
        ))

        # ---------- BROCHURES ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath(
                "//a[contains(@class,'btn-file')]/@href"
            )
        ]

        # ---------- SINGLE AGENT ---------- #
        agent_name = ""
        agent_phone = ""

        agent = tree.xpath("//div[@class='contactUser'][1]")

        if agent:
            agent = agent[0]

            agent_name = self._clean(" ".join(
                agent.xpath(".//h3//text()")
            ))

            agent_phone = self._clean(" ".join(
                agent.xpath(
                    ".//div[contains(@class,'contactUser__details')]//p[1]/text()"
                )
            ))

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Gale Priggen & Co",
            "agentName": agent_name,
            "agentCity": "London",
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

        # ===================== SQUARE FEET ===================== #
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*feet)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        # ===================== SQUARE METRES ===================== #
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
                size_ft = round(sqm_value * 10.7639, 3)  # convert sqm → sqft

        # ===================== ACRES ===================== #
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac\.?)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        # ===================== HECTARES ===================== #
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
                size_ac = round(hectare_value * 2.47105, 3)  # convert ha → acres

        return size_ft, size_ac

    def extract_tenure(self, text):
        if not text:
            return ""
        t = text.lower()
        if "freehold" in t:
            return "Freehold"
        if "leasehold" in t:
            return "Leasehold"
        return ""

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

    def _clean(self, val):
        return " ".join(val.split()) if val else ""