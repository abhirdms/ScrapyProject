import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class HowseAssociatesScraper:
    BASE_URL = "https://www.howseassociates.co.uk/"
    DOMAIN = "https://www.howseassociates.co.uk"
    AGENT_COMPANY = "Howse Associates"

    def __init__(self):
        self.results = []
        self.seen_titles = set()

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")

        service = Service("/usr/bin/chromedriver")
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 10)

    # ======================================================
    # RUN
    # ======================================================

    def run(self):
        self.driver.get(self.BASE_URL)

        try:
            self.wait.until(EC.presence_of_element_located(
                (By.XPATH, "//span[@class='BSBTitle']")
            ))
        except Exception:
            self.driver.quit()
            return self.results

        while True:
            tree = html.fromstring(self.driver.page_source)

            title = self._clean(" ".join(
                tree.xpath("//span[@class='BSBTitle']/text()")
            ))

            if not title:
                break

            # Always scrape current property
            if title not in self.seen_titles:
                obj = self.parse_listing(tree, self.driver.current_url)
                if obj:
                    self.results.append(obj)
                    self.seen_titles.add(title)

            # Check if next button exists
            next_buttons = self.driver.find_elements(
                By.XPATH,
                "//a[contains(text(),'Next property')]"
            )

            if not next_buttons:
                break   # true end — no next button

            old_title = title
            next_buttons[0].click()

            try:
                self.wait.until(
                    lambda d: d.find_element(
                        By.XPATH,
                        "//span[@class='BSBTitle']"
                    ).text.strip() != old_title
                )
            except:
                break   # title did not change → end

            # If we loop back to first property, stop
            new_title = self.driver.find_element(
                By.XPATH,
                "//span[@class='BSBTitle']"
            ).text.strip()

            if new_title in self.seen_titles:
                break

        self.driver.quit()
        return self.results



    # ======================================================
    # PARSE LISTING
    # ======================================================

    def parse_listing(self, tree, current_url):

        display_address = self._clean(" ".join(
            tree.xpath("//span[@class='BSBTitle']/text()")
        ))

        if not display_address:
            return None

        content_text = self._clean(" ".join(
            tree.xpath("//div[@class='mainPagePropertiesContentContainer']//text()")
        ))

        detailed_description = self._clean(" ".join(
            tree.xpath("//div[@class='mainPagePropertiesContentContainer']//p//text()")
        ))

        # ---------- BROCHURE ----------
        brochure_urls = [
            href.strip()
            for href in tree.xpath("//a[contains(@href,'drive.google.com')]/@href")
        ]

        # Use first brochure as listingUrl
        if brochure_urls:
            listing_url = brochure_urls[0]
        else:
            # If absolutely no brochure, fallback to current URL
            listing_url = current_url

        # ---------- IMAGES ----------
        raw_images = tree.xpath("//img[@class='homePropertyImage']/@src")

        property_images = []
        for src in raw_images:
            if not src or "trans.gif" in src.lower():
                continue
            full = urljoin(self.DOMAIN, src.strip())
            if full not in property_images:
                property_images.append(full)

        # ---------- EXTRACTIONS ----------
        sale_type = self.normalize_sale_type(content_text)
        size_ft, size_ac = self.extract_size(content_text)
        tenure = self.extract_tenure(content_text)
        price = self.extract_numeric_price(content_text, sale_type)
        postcode = self.extract_postcode(display_address)

        obj = {
            "listingUrl": listing_url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": postcode,
            "brochureUrl": brochure_urls,  # keep full list
            "agentCompanyName": self.AGENT_COMPANY,
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

    # ======================================================
    # HELPERS
    # ======================================================

    def extract_size(self, text):
        if not text:
            return "", ""

        SQM_TO_SQFT = 10.7639
        HECTARE_TO_ACRE = 2.47105

        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        # SQ FT
        m = re.search(r'(\d+(?:\.\d+)?)\s*(sq\.?\s*ft|sqft|sf)\b', text)
        if m:
            return round(float(m.group(1)), 3), ""

        # SQM
        m = re.search(r'(\d+(?:\.\d+)?)\s*(sqm|m2|m²)\b', text)
        if m:
            return round(float(m.group(1)) * SQM_TO_SQFT, 3), ""

        # ACRES
        m = re.search(r'(\d+(?:\.\d+)?)\s*(acres?|acre|ac)\b', text)
        if m:
            return "", round(float(m.group(1)), 3)

        # HECTARES
        m = re.search(r'(\d+(?:\.\d+)?)\s*(hectares?|ha)\b', text)
        if m:
            return "", round(float(m.group(1)) * HECTARE_TO_ACRE, 3)

        return "", ""

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale":
            return ""

        t = text.lower().replace(",", "")

        # Explicit Price:
        m = re.search(r'price:\s*£?\s*(\d+(?:\.\d+)?)', t)
        if m:
            return str(int(float(m.group(1))))

        prices = re.findall(r'£\s*(\d{5,})', t)
        if prices:
            return str(min(int(p) for p in prices))

        return ""

    def extract_tenure(self, text):
        t = text.lower()
        if "freehold" in t:
            return "Freehold"
        if "leasehold" in t:
            return "Leasehold"
        return ""

    def extract_postcode(self, text):
        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'
        t = text.upper()
        m = re.search(FULL, t) or re.search(PARTIAL, t)
        return m.group() if m else ""

    def normalize_sale_type(self, text):
        t = text.lower()
        if "price:" in t:
            return "For Sale"
        if "rent:" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
