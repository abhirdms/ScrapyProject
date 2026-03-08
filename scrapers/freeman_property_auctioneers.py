import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class FreemanFormanScraper:
    BASE_URL = "https://www.freemanforman.co.uk/properties/sales/most-recent-first/"
    DOMAIN = "https://www.freemanforman.co.uk"

    def __init__(self):
        self.results = []
        self.seen_urls = set()

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        service = Service("C:/Users/educa/Downloads/ScrapyProject/ScrapyProject/chromedriver.exe")
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 20)

    # ===================== RUN ===================== #

    def run(self):
        page = 1

        while True:
            page_url = self.BASE_URL if page == 1 else f"{self.BASE_URL}page-{page}"
            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'card--image') and contains(@class,'card--list')]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            # ❌ Skip SOLD properties
            cards = tree.xpath(
                "//div[contains(@class,'card--image') and contains(@class,'card--list')]"
                "[not(.//li[contains(@class,'tag--status')]//span[contains(.,'SOLD')])]"
            )

            if not cards:
                break

            for card in cards:
                href = card.xpath(".//a[contains(@class,'card__link')]/@href")
                if not href:
                    continue

                url = urljoin(self.DOMAIN, href[0])

                if url in self.seen_urls:
                    continue
                self.seen_urls.add(url)

                try:
                    obj = self.parse_listing(url, card)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

            page += 1

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url, card_node):
        # ---------- LISTING PAGE FIELDS ---------- #

        price = self._clean("".join(
            card_node.xpath(".//p[contains(@class,'card__heading')]/text()")
        ))

        display_address = self._clean("".join(
            card_node.xpath(".//p[contains(@class,'card__text-content')][1]/text()")
        ))

        property_sub_type = self._clean("".join(
            card_node.xpath(".//span[contains(@class,'card__text-title')]/text()")
        ))

        beds = self._first(card_node.xpath(
            "(.//ul[contains(@class,'card-content__spec-list')]"
            "//span[contains(@class,'card-content__spec-list-number')])[1]/text()"
        ))

        baths = self._first(card_node.xpath(
            "(.//ul[contains(@class,'card-content__spec-list')]"
            "//span[contains(@class,'card-content__spec-list-number')])[2]/text()"
        ))

        receptions = self._first(card_node.xpath(
            "(.//ul[contains(@class,'card-content__spec-list')]"
            "//span[contains(@class,'card-content__spec-list-number')])[3]/text()"
        ))

        listing_image = self._first(card_node.xpath(
            ".//img[contains(@class,'property-card-image')]/@src"
        ))
        if listing_image and listing_image.startswith("//"):
            listing_image = "https:" + listing_image

        # ---------- DETAIL PAGE ---------- #
        self.driver.get(url)

        try:
            self.wait.until(EC.presence_of_element_located((
                By.XPATH, "//div[@id='property-carousel']"
            )))
        except Exception:
            return None

        tree = html.fromstring(self.driver.page_source)

        # ---------- DESCRIPTION ---------- #
        detailed_description = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'property-details')]//p//text()")
        ))

        # ---------- MEDIA ---------- #
        media = []

        # Video
        video = tree.xpath("//iframe[contains(@class,'carousel__video')]/@src")
        media.extend(video)

        # Try clicking PHOTOS tab
        try:
            photos_tab = self.driver.find_element(
                By.XPATH,
                "//a[contains(@class,'details-panel__options-link')]"
                "//span[normalize-space()='PHOTOS']/ancestor::a"
            )
            self.driver.execute_script("arguments[0].click();", photos_tab)
        except Exception:
            pass

        tree = html.fromstring(self.driver.page_source)

        # Images
        images = tree.xpath(
            "//div[@id='property-carousel']//li[contains(@class,'slide')]//img/@src"
        )
        for img in images:
            if img.startswith("//"):
                img = "https:" + img
            media.append(img)

        # Floorplan
        floorplans = tree.xpath("//a[contains(@href,'floorplan')]/@href")
        for fp in floorplans:
            if fp.startswith("//"):
                fp = "https:" + fp
            media.append(fp)

        # EPC
        epc = tree.xpath("//img[contains(@alt,'EPC')]/@src")
        for e in epc:
            if e.startswith("//"):
                e = "https:" + e
            media.append(e)

        # Fallback image
        fallback = tree.xpath(
            "//div[contains(@class,'property-calculator__image-container')]//img/@src"
        )
        media.extend(fallback)

        # Deduplicate media
        property_images = list(dict.fromkeys(
            [m for m in media if m]
        ))

        # ---------- PRICE NORMALIZE ---------- #
        numeric_price = self.extract_numeric_price(price)

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": numeric_price,
            "propertySubType": property_sub_type,
            "bedrooms": beds,
            "bathrooms": baths,
            "receptions": receptions,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "postalCode": self.extract_postcode(display_address),
            "agentCompanyName": "Freeman Forman",
        }

        print("*****" * 10)
        print(obj)
        print("*****" * 10)

        return obj

    # ===================== HELPERS ===================== #

    def extract_numeric_price(self, text):
        if not text:
            return ""
        t = text.lower().replace(",", "")
        m = re.search(r'£\s*(\d+(?:\.\d+)?)', t)
        return m.group(1) if m else ""

    def extract_postcode(self, text):
        if not text:
            return ""
        text = text.upper()
        m = re.search(r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b', text)
        return m.group(0) if m else ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""

    def _first(self, arr):
        return arr[0].strip() if arr else ""
    