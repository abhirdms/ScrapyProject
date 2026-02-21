import re
from urllib.parse import urljoin, urlparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class PudneyShuttleworthScraper:
    BASE_URLS = [
        "https://www.pudneyshuttleworth.co.uk/in-town-retail",
        "https://www.pudneyshuttleworth.co.uk/our",
        "https://www.pudneyshuttleworth.co.uk/out-of-town-retail",
    ]
    DOMAIN = "https://www.pudneyshuttleworth.co.uk"
    AGENT_COMPANY = "Pudney Shuttleworth"

    def __init__(self):
        self.results = []
        self.seen_keys = set()

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
        for url in self.BASE_URLS:
            self.driver.get(url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[@role='listitem']"
                )))
            except Exception:
                continue

            self._expand_view_more()
            tree = html.fromstring(self.driver.page_source)
            items = tree.xpath("//div[@role='listitem']")

            for item in items:
                try:
                    obj = self.parse_listing(item, url)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, item, source_url):
        p_values = []
        for p in item.xpath(".//div[@data-testid='richTextElement']//p"):
            txt = self._clean(" ".join(p.xpath(".//text()")))
            if txt:
                p_values.append(txt)

        size_text = ""
        for v in p_values:
            if self._looks_like_size(v):
                size_text = v
                break

        non_size = [v for v in p_values if v != size_text]
        scheme = non_size[0] if non_size else ""
        location = non_size[1] if len(non_size) > 1 else ""

        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in item.xpath(".//a[contains(@href,'.pdf')]/@href")
        ]
        listing_url = brochure_urls[0] if brochure_urls else source_url

        unique_key = "|".join([listing_url, scheme, location, size_text])
        if unique_key in self.seen_keys:
            return None
        self.seen_keys.add(unique_key)

        size_ft, size_ac = self.extract_size(size_text)
        category = self.url_to_category(source_url)
        detailed_description = self._clean(
            f"Category: {category}. Scheme: {scheme}. Location: {location}. Size: {size_text}."
        )

        obj = {
            "listingUrl": listing_url,
            "displayAddress": location,
            "price": "",
            "propertySubType": scheme,
            "propertyImage": [],
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(location),
            "brochureUrl": brochure_urls,
            "agentCompanyName": self.AGENT_COMPANY,
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": "",
            "saleType": "",
        }

        print("*****" * 10)
        print(obj)
        print("*****" * 10)

        return obj

    # ===================== HELPERS ===================== #

    def _expand_view_more(self):
        while True:
            try:
                cards_before = len(self.driver.find_elements(By.XPATH, "//div[@role='listitem']"))
                btn = WebDriverWait(self.driver, 2).until(
                    EC.element_to_be_clickable((
                        By.XPATH,
                        "//button[normalize-space()='View More' or .//span[normalize-space()='View More']]"
                    ))
                )
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                self.driver.execute_script("arguments[0].click();", btn)

                WebDriverWait(self.driver, 6).until(
                    lambda d: len(d.find_elements(By.XPATH, "//div[@role='listitem']")) > cards_before
                )
            except Exception:
                break

    def _looks_like_size(self, text):
        t = text.lower()
        return bool(re.search(r"\b(sq\.?\s*ft|sqft|sq\s*ft|sf|acres?|acre)\b", t))

    def url_to_category(self, url):
        path = urlparse(url).path.strip("/").replace("-", " ")
        return " ".join(w.capitalize() for w in path.split()) if path else ""

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\.?\s*ft|sqft|sf)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        return size_ft, size_ac

    def extract_postcode(self, text):
        if not text:
            return ""

        full = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        partial = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        t = text.upper()
        m = re.search(full, t) or re.search(partial, t)
        return m.group() if m else ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
