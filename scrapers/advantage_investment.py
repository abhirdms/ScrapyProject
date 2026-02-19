import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class AdvantageInvestmentScraperaashishgiri:
    BASE_URL = "https://advantageinvestment.co.uk/investment-properties/"
    DOMAIN = "https://advantageinvestment.co.uk"

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
            "//div[contains(@class,'jet-listing-grid__item')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            "//div[contains(@class,'jet-listing-grid__item')]"
            "//a[contains(@class,'jet-listing-dynamic-link__link')]/@href"
        )

        for url in listing_urls:
            try:
                full_url = urljoin(self.DOMAIN, url)
                self.results.append(self.parse_listing(full_url))
            except Exception:
                continue

        self.driver.quit()
        return self.results

    # ---------------- LISTING ---------------- #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[@data-id='fa1d31b']"
        )))

        tree = html.fromstring(self.driver.page_source)

        display_address = self._clean(" ".join(
            tree.xpath(
                "//div[@class='jet-breadcrumbs__item']//span[@class='jet-breadcrumbs__item-target']/text()"
            )
        ))

        price_text = " ".join(
            tree.xpath(
                "//div[@class='jet-listing-dynamic-field__content'][contains(text(),'Prices From')]/text()"
            )
        )
        price = self.extract_price(price_text)

        images = [
            img for img in tree.xpath(
                "//div[contains(@class,'elementor-image-carousel')]"
                "//img[@class='swiper-slide-image']/@src"
            )
        ]

        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//div[@data-id='fa1d31b']//div[contains(@class,'jet-listing-dynamic-field__content')]//text()"
            )
        ))

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": images,
            "detailedDescription": detailed_description,
            "sizeFt": "",
            "sizeAc": "",
            "postalCode": "",
            "brochureUrl": "",
            "agentCompanyName": "Advantage Investment",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": "",
            "saleType": "",
        }

        return obj

    # ---------------- HELPERS ---------------- #

    def extract_price(self, text):
        if not text:
            return ""

        text = text.replace(",", "")
        m = re.search(r"£\s?(\d+(?:\.\d+)?)", text)
        return m.group(1) if m else ""

    def _clean(self, text):
        if not text:
            return ""
        return re.sub(r"\s+", " ", text).strip()
