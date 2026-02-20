import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class PK3AgencyScraper:
    BASE_URL = "https://pk3.agency/investments/"
    DOMAIN = "https://pk3.agency"

    def __init__(self):
        self.results = []

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
            "//article[contains(@class,'property-card')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        cards = tree.xpath("//article[contains(@class,'property-card')]")

        for card in cards:
            try:
                rel_url = card.xpath(".//a[@class='property-card-link']/@href")[0]
                url = urljoin(self.DOMAIN, rel_url)

                # PROPERTY TYPE FROM LISTING PAGE
                sector = self._clean(" ".join(
                    card.xpath(".//span[@class='property-card-sector']/text()")
                ))

                # SALE TYPE FROM LISTING PAGE
                status = card.get("data-status", "").strip().lower()

                if status == "available":
                    sale_type = "For Sale"
                elif status == "under-offer":
                    sale_type = "For Sale"
                elif status == "to let":
                    sale_type = "To Let"
                else:
                    sale_type = ""

                self.results.append(
                    self.parse_listing(url, sector, sale_type)
                )

            except Exception:
                continue

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url, sector, sale_type):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//section[contains(@class,'hero')]//h1"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------------- ADDRESS ---------------- #
        display_address = self._clean(" ".join(
            tree.xpath("//section[contains(@class,'hero')]//h1/text()")
        ))

        if not display_address:
            display_address = self._clean(" ".join(
                tree.xpath("//section[contains(@class,'hero')]/@aria-label")
            ))

        # ---------------- DESCRIPTION ---------------- #
        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//div[@class='property-description']"
                "//div[contains(@class,'property-content')]//*[self::p or self::li]//text()"
            )
        ))

        # ---------------- SIZE EXTRACTION ---------------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------------- PRICE ---------------- #
        if sale_type == 'For Sale':
            price_text = self._clean(" ".join(
                tree.xpath(
                    "//div[@class='property-image-block']"
                    "//span[@class='property-metric-label' and text()='Price']"
                    "/following-sibling::span[@class='property-metric-value']/text()"
                )
            ))
        else:
            price_text = ""

        # ---------------- EMAIL (FIXED) ---------------- #
        emails = tree.xpath("//a[starts-with(@href,'mailto:')]/@href")

        clean_emails = []
        for e in emails:
            e = e.replace("mailto:", "").strip().lower()
            if e and e not in clean_emails:
                clean_emails.append(e)

        agent_email = clean_emails[0] if clean_emails else ""

        # ---------------- OBJECT ---------------- #
        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": self.extract_numeric_price(price_text),
            "propertySubType": sector,
            "propertyImage": [
                img for img in tree.xpath(
                    "//div[@class='property-image-block']"
                    "//img[contains(@class,'property-thumbnail-image')]/@src"
                )
            ],
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": [
                urljoin(self.DOMAIN, u)
                for u in tree.xpath(
                    "//div[contains(@class,'property-card-box')]//a[@target='_blank']/@href"
                )
            ],
            "agentCompanyName": "PK3 Agency",
            "agentName": self._clean(" ".join(
                tree.xpath(
                    "//p[contains(@class,'property-card-box-text')]//a[not(starts-with(@href,'mailto:'))]/text()"
                )
            )),
            "agentCity": "",
            "agentEmail": agent_email,
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": "",
            "saleType": sale_type,
        }

        return obj

    # ===================== HELPERS ===================== #

    def extract_postcode(self, text):
        if not text:
            return ""

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        text = text.upper()
        m = re.search(FULL, text) or re.search(PARTIAL, text)
        return m.group().strip() if m else ""

    def extract_numeric_price(self, text):
        if not text:
            return ""

        raw = text.lower()

        if any(k in raw for k in [
            "poa",
            "price on application",
            "on application",
            "subject to contract"
        ]):
            return ""

        raw = raw.replace("£", "").replace(",", "")
        raw = re.sub(r"(to|–|—)", "-", raw)

        numbers = re.findall(r"\d+(?:\.\d+)?", raw)
        if not numbers:
            return ""

        price = min(float(n) for n in numbers)
        return str(int(price)) if price.is_integer() else str(price)
    

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

    def _clean(self, val):
        return val.strip() if val else ""