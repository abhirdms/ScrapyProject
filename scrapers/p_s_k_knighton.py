import re
from urllib.parse import urljoin, urlparse, parse_qs

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class PSKKnightonScraper:
    BASE_URL = "http://www.pskknighton.co.uk/site/go/search?sales=false"
    DOMAIN = "http://www.pskknighton.co.uk"

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
        self.driver.get(self.BASE_URL)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[@id='searchResults']"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            "//div[@id='searchResults']//td[@class='thumbnail']//a/@href"
        )

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

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[@id='particularsContainer']"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//div[@id='propertyPrice']/p[@class='center']/text()")
        ))

        # ---------- DESCRIPTION ---------- #
        detailed_description = self._clean(" ".join(
            tree.xpath("//h4[text()='Description']/following-sibling::p[1]//text()")
        ))

        # ---------- SIZE (Feature list first) ---------- #
        size_text = " ".join(
            tree.xpath(
                "//table[@class='featureList']//li[contains(text(),'sq ft')]//text()"
            )
        )

        if not size_text:
            size_text = detailed_description

        size_ft, size_ac = self.extract_size(size_text)

        # ---------- PRICE (RENT extraction) ---------- #
        price = self.extract_rent_price(detailed_description)

        # ---------- PROPERTY TYPE ---------- #
        property_sub_type = self._clean(" ".join(
            tree.xpath("//tr[@class='propertyDetails']//td[@class='propertyType']/text()")
        ))

        # ---------- IMAGES ---------- #
        property_images = [
            urljoin(self.DOMAIN, src)
            for src in tree.xpath("//div[@id='thumbs']//img/@src")
        ]

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(text(),'Download PDF Brochure')]/@href")
        ]

        # ---------- POSTCODE (from Google map link) ---------- #
        map_link = tree.xpath(
            "//div[@id='environmental']//a[contains(@href,'maps?q=')]/@href"
        )
        postal_code = ""

        if map_link:
            parsed = urlparse(map_link[0])
            qs = parse_qs(parsed.query)
            if "q" in qs:
                postal_code = qs["q"][0]

        # ---------- AGENT DETAILS ---------- #
        agent_email = self._clean(" ".join(
            tree.xpath(
                "//h4[normalize-space()='Additional Information']"
                "/following-sibling::p//a[starts-with(@href,'mailto:')]/text()"
            )
        ))

        agent_phone = self._clean(" ".join(
            tree.xpath(
                "//h4[normalize-space()='Additional Information']"
                "/following-sibling::p//strong/text()"
            )
        ))

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": postal_code,
            "brochureUrl": brochure_urls,
            "agentCompanyName": "PSK Knighton",
            "agentName": "",
            "agentCity": "",
            "agentEmail": agent_email,
            "agentPhone": agent_phone,
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": "",
            "saleType": "To Let",
        }

        print("*****" * 10)
        print(obj)
        print("*****" * 10)

        return obj

    # ===================== HELPERS ===================== #

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        # SQ FT
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\.?\s*ft\.?|sqft|sf)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        return size_ft, size_ac

    def extract_rent_price(self, text):
        if not text:
            return ""

        t = text.lower()

        # Look for £xx per sq ft
        m = re.search(r'£\s*(\d+(?:\.\d+)?)', t)
        if m:
            return str(int(float(m.group(1))))

        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""