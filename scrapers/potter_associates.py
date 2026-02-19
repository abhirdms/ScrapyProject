import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class PotterAssociatesScraperaashishgiri:
    BASE_URL = "https://www.potterassociates.co.uk/search-results/?department=commercial&location=&minimum_price=&maximum_price=&minimum_rent=&maximum_rent=&minimum_bedrooms=&minimum_floor_area=&maximum_floor_area=&commercial_property_type="
    DOMAIN = "https://www.potterassociates.co.uk"

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

    # ---------------- RUN ---------------- #

    def run(self):
        self.driver.get(self.BASE_URL)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//ul[@class='properties clear']/li"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            "//ul[@class='properties clear']/li//h3/a/@href"
        )

        for rel_url in listing_urls:
            try:
                url = urljoin(self.DOMAIN, rel_url)
                self.results.append(self.parse_listing(url))
            except Exception:
                continue

        self.driver.quit()
        return self.results

    # ---------------- LISTING ---------------- #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h1[@class='elementor-heading-title elementor-size-default']"
        )))

        tree = html.fromstring(self.driver.page_source)

        display_address = self._clean(" ".join(
            tree.xpath("//h1[@class='elementor-heading-title elementor-size-default']/text()")
        ))

        price = self._clean(" ".join(
            tree.xpath("//span[contains(@class,'commercial-rent')]/text()")
        ))

        property_images = [
            urljoin(self.DOMAIN, img)
            for img in tree.xpath(
                "//div[@class='ph-elementor-gallery']//a[@data-fancybox='elementor-gallery']/@href"
            )
        ]

        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'features')]//li/text() | "
                "//div[contains(@class,'summary-contents')]//text()[normalize-space()] | "
                "//div[contains(@class,'description-contents')]//text()[normalize-space()]"
            )
        ))

        size_ft = self.extract_size_from_text(detailed_description)

        agent_name = self.extract_agent_name(detailed_description)
        agent_email = self.extract_email(detailed_description)
        agent_phone = self.extract_phone(detailed_description)

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",

            "propertyImage": property_images,
            "detailedDescription": detailed_description,

            "sizeFt": size_ft,
            "sizeAc": "",

            "postalCode": self.extract_postcode(display_address),

            "brochureUrl": self._clean(" ".join(
                tree.xpath("//li[contains(@class,'action-brochure')]//a/@href")
            )),

            "agentCompanyName": "Potter Associates",
            "agentName": agent_name,
            "agentCity": "",
            "agentEmail": agent_email,
            "agentPhone": agent_phone,
            "agentStreet": "",
            "agentPostcode": "",

            "tenure": "",
            "saleType": "",
        }

        return obj

    # ---------------- HELPERS ---------------- #

    def extract_size_from_text(self, text):
        if not text:
            return ""

        text = text.lower().replace(",", "")
        m = re.search(r'(\d+(?:\.\d+)?)\s*(sq\s*ft|sqft|sf)', text)
        if m:
            return int(float(m.group(1)))
        return ""

    def extract_postcode(self, text):
        if not text:
            return ""
        m = re.search(r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b', text, re.I)
        return m.group(0) if m else ""

    def extract_email(self, text):
        if not text:
            return ""
        m = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        return m.group(0) if m else ""

    def extract_phone(self, text):
        if not text:
            return ""
        m = re.search(r'(\+?\d[\d\s]{8,})', text)
        return m.group(1).strip() if m else ""

    def extract_agent_name(self, text):
        if not text:
            return ""
        m = re.search(r'agent\s+([A-Za-z\s]+)\s*T:', text, re.I)
        return m.group(1).strip() if m else ""

    def _clean(self, value):
        return re.sub(r'\s+', ' ', value or "").strip()
