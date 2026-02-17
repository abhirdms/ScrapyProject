import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class KimmreScraper:
    SALES_URL = "https://www.kimmre.com/sales"
    LETTINGS_URL = "https://www.kimmre.com/lettings"
    DOMAIN = "https://www.kimmre.com"

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
        self.scrape_sales()
        self.scrape_lettings()
        self.driver.quit()
        return self.results

    # ===================== SALES ===================== #

    def scrape_sales(self):
        page = 1

        while True:
            url = f"{self.SALES_URL}?9dc047e8_page={page}"
            self.driver.get(url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'sales-collection-item')]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            cards = tree.xpath("//div[contains(@class,'sales-collection-item')]")
            if not cards:
                break

            for card in cards:

                status = self._clean(" ".join(
                    card.xpath(
                        ".//div[contains(@class,'sales-card-tag')]"
                        "//div[contains(@class,'body-text')]/text()"
                    )
                )).lower()

                # Skip if not live
                if status != "live":
                    continue
                brochure = card.xpath(
                    ".//a[contains(@class,'live-sales-button')]/@href"
                )
                if not brochure:
                    continue

                listing_url = urljoin(self.DOMAIN, brochure[0])

                if listing_url in self.seen_urls:
                    continue
                self.seen_urls.add(listing_url)

                title = self._clean(" ".join(
                    card.xpath(".//div[contains(@class,'sale-heading')]/text()")
                ))

                price_text = self._clean(" ".join(
                    card.xpath(".//p[contains(@class,'sale-price')]/text()")
                ))

                description = self._clean(" ".join(
                    card.xpath(".//p[contains(@class,'sales-details')]/text()")
                ))

                image = card.xpath(".//img/@src")
                image = image[0] if image else ""

                size_ft, size_ac = self.extract_size(description)
                price = self.extract_numeric_price(price_text, "For Sale")

                tenure = self.extract_tenure(description)

                obj = {
                    "listingUrl": listing_url,
                    "displayAddress": title,
                    "price": price,
                    "propertySubType": "",
                    "propertyImage": image,
                    "detailedDescription": description,
                    "sizeFt": size_ft,
                    "sizeAc": size_ac,
                    "postalCode": self.extract_postcode(title),
                    "brochureUrl": [listing_url],
                    "agentCompanyName": "Kimmre",
                    "agentName": "",
                    "agentCity": "",
                    "agentEmail": "",
                    "agentPhone": "",
                    "agentStreet": "",
                    "agentPostcode": "",
                    "tenure": tenure,
                    "saleType": "For Sale",
                }

                self.results.append(obj)

            page += 1

    # ===================== LETTINGS ===================== #

    def scrape_lettings(self):
        self.driver.get(self.LETTINGS_URL)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'sales-collection-item')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_links = tree.xpath(
            "//a[@data-element='link']/@href"
        )

        for href in listing_links:
            url = urljoin(self.DOMAIN, href)

            if url in self.seen_urls:
                continue
            self.seen_urls.add(url)

            try:
                obj = self.parse_letting_detail(url)
                if obj:
                    self.results.append(obj)
            except Exception:
                continue

    # ===================== LETTING DETAIL ===================== #

    def parse_letting_detail(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h1[@class='heading-letting-heading']"
        )))

        tree = html.fromstring(self.driver.page_source)

        title = self._clean(" ".join(
            tree.xpath("//h1[@class='heading-letting-heading']/text()")
        ))

        short_desc = self._clean(" ".join(
            tree.xpath("//p[@class='lettings-heading-support-text']/text()")
        ))

        property_type = self._clean(" ".join(
            tree.xpath("//li[.//div[text()='Property type']]/div[2]/text()")
        ))

        sale_type_raw = self._clean(" ".join(
            tree.xpath("//li[.//div[text()='Tenure']]/div[2]/text()")
        ))

        sale_type = self.normalize_sale_type(sale_type_raw)



        size_text = self._clean(" ".join(
            tree.xpath("//li[.//div[text()='Size']]/div[2]//text()")
        ))

        size_ft, size_ac = self.extract_size(size_text)

        key_features = self._clean(" ".join(
            tree.xpath("//div[text()='Key Features']/following-sibling::div//text()")
        ))

        specifications = self._clean(" ".join(
            tree.xpath("//div[text()='Specifications']/following-sibling::div//text()")
        ))

        detailed_description = " ".join(
            part for part in [short_desc, key_features, specifications] if part
        )

        tenure = self.extract_tenure(detailed_description)

        image = tree.xpath("//img[contains(@class,'lettings-fw-image')]/@src")
        image = image[0] if image else ""

        agent_name = self._clean(" ".join(
            tree.xpath("(//div[@class='team-name']/text())[1]")
        ))

        agent_phone = self._clean(" ".join(
            tree.xpath("(//a[contains(@href,'tel:')]/text())[1]")
        ))

        agent_email = ""

        email = tree.xpath(
            "(//div[contains(@class,'team-card-name-small')][1]"
            "//a[contains(@class,'team-email')]/@href)"
        )

        if email:
            agent_email = email[0].replace("mailto:", "")

        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
        ]

        obj = {
            "listingUrl": url,
            "displayAddress": title,
            "price": "",
            "propertySubType": property_type,
            "propertyImage": image,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(title),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Kimmre",
            "agentName": agent_name,
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

    def normalize_sale_type(self, text):
        t = text.lower()
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        if "under offer" in t:
            return "For Sale"
        return ""


    def extract_tenure(self, text):
        if not text:
            return ""

        t = text.lower()
        if "freehold" in t:
            return "Freehold"
        if "leasehold" in t:
            return "Leasehold"
        return ""

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\s*ft|sqft|sf)', text)
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac)', text)
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

        m = re.search(r'[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?', t)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))
        if "m" in m.group(0):
            num *= 1_000_000

        return str(int(num))


    def extract_postcode(self, text):
        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        t = text.upper()
        m = re.search(FULL, t) or re.search(PARTIAL, t)
        return m.group() if m else ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
