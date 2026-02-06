import requests
import re
from lxml import html
from utils import store_data_to_csv


class GlinsmanWellerScraper:
    BASE_SEARCH = "https://www.glinsmanweller.co.uk/current-disposals/"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/144.0.0.0 Safari/537.36"
        )
    }

    def __init__(self):
        self.results = []

    # ---------------- RUN ---------------- #

    def run(self):
        page = 1

        while True:
            url = self._build_page_url(page)

            resp = requests.get(url, headers=self.HEADERS, timeout=30)
            if resp.status_code != 200:
                break

            tree = html.fromstring(resp.text)

            # OUTER PAGE
            listing_urls = tree.xpath(
                "//h3[contains(@class,'card-title')]/a/@href"
            )

            if not listing_urls:
                break

            for link in listing_urls:
                try:
                    self.results.append(self.parse_listing(link))

                except Exception:
                    continue
            break

        return self.results

    def _build_page_url(self, page):
        # Site has no pagination but keeping SAME STRUCTURE
        return self.BASE_SEARCH

    # ---------------- LISTING ---------------- #

    def parse_listing(self, url):
        resp = requests.get(url, headers=self.HEADERS, timeout=30)
        tree = html.fromstring(resp.text)

        description = self.get_description(tree)

        size_ft, size_ac = self.extract_size(tree)

        images = tree.xpath(
            "//div[contains(@class,'elementor-gallery__container')]//a[contains(@class,'e-gallery-item')]/@href"
        )

        if not images:
            images = tree.xpath(
                "//div[contains(@class,'elementor-widget-container')]//a/@href"
            )

        display_address = self._clean(" ".join(tree.xpath(
            "//div[@class='elementor-widget-container']/h1/text()"
        )))

        obj = {
            "listingUrl": url,

            "displayAddress": display_address,

            "price": "", #not working currectly no connectin with sale type

            "propertySubType": "",

            "propertyImage": list(dict.fromkeys(images)),


            "detailedDescription": description,

            "sizeFt": size_ft,
            "sizeAc": size_ac,

            "postalCode": self.extract_postcode(display_address),

            "brochureUrl": self._clean(" ".join(tree.xpath(
                "//a[text()='Brochure' and contains(@href,'.pdf')]/@href"
            ))),

            "agentCompanyName": "Glinsman Weller",
            "agentName": "",

            "agentCity": "",

            "agentEmail": "",

            "agentPhone": "",

            "agentStreet": "",
            "agentPostcode": "",

            "tenure": self.get_tenure(tree),

            "saleType": self.get_sale_type(tree),
        }

        return obj

    # ------------- helpers ------------ #

    def get_sale_type(self, tree):
        text = self._clean(" ".join(tree.xpath(
            "//div[@class='homebadge']/text()"
        ))).lower()

        if not text:
            return ""

        if "sale" in text:
            return "For Sale"

        if "to let " in text:
            return "To Let"

        return ""



    def get_description(self, tree):
        texts = tree.xpath(
            "//div[@data-widget_type='theme-post-content.default']//p//text()"
        )
        return " ".join(t.strip() for t in texts if t.strip())

    def get_tenure(self, tree):
        text = " ".join(tree.xpath(
            "//div[@data-widget_type='theme-post-content.default']//p//text()"
        )).lower()

        if "freehold" in text:
            return "Freehold"
        elif "leasehold" in text:
            return "Leasehold"
        return ""

    def extract_size(self, tree):
        text = " ".join(tree.xpath(
            "//div[@class='row']//div[contains(text(),'sq ft') or contains(text(),'acre')]//text()"
        ))

        if not text:
            return "", ""

        text = text.lower().replace(",", "")

        size_ft = ""
        size_ac = ""

        # -------- SQ FT (ONLY IF PRESENT) --------
        m = re.search(r'(\d+(?:\.\d+)?)\s*sq\s*ft', text)
        if m:
            size_ft = int(float(m.group(1)))

        # -------- ACRES (ONLY IF PRESENT, NO CONVERSION) --------
        m = re.search(r'(\d+(?:\.\d+)?)\s*(acres?|acre|ac)\b', text)
        if m:
            size_ac = round(float(m.group(1)), 4)

        return size_ft, size_ac


    def extract_postcode(self, text):
        if not text:
            return ""

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        text = text.upper()
        match = re.search(FULL, text) or re.search(PARTIAL, text)
        return match.group().strip() if match else ""

    def _clean(self, val):
        return val.strip() if val else ""
