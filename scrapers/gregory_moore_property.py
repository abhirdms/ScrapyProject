import requests
from lxml import html
import re
from urllib.parse import urljoin


class GregoryMoorePropertyScraper:
    BASE_URL = "https://www.gregorymooreproperty.co.uk/new-instructions/"

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
        resp = requests.get(self.BASE_URL, headers=self.HEADERS, timeout=30)
        if resp.status_code != 200:
            return []

        tree = html.fromstring(resp.text)

        listings = tree.xpath(
            "//div[@id='gallery-1']//dl[contains(@class,'gallery-item')]"
        )

        for el in listings:
            try:
                self.results.append(self.parse_listing(el))
            except Exception:
                continue

        return self.results

    # ---------------- LISTING ---------------- #

    def parse_listing(self, el):
        caption_texts = [
            t.strip() for t in el.xpath(
                ".//dd[contains(@class,'gallery-caption')]/text()"
            ) if t.strip()
        ]

        display_address = caption_texts[0] if len(caption_texts) >= 1 else ""

        # ⬇️ use FULL caption text for postcode extraction
        caption_full_text = " ".join(caption_texts)
        postal_code = self.extract_postcode(caption_full_text)
        raw_brochures = el.xpath(".//dt//a/@href")


        obj = {
            "listingUrl": (
                self.normalize_url(raw_brochures[0])
                if raw_brochures else ""
            ),

            "displayAddress": display_address,

            "price": "",

            "propertySubType": "",

            "propertyImage": el.xpath(
                ".//dt//img/@src"
            ),

            "detailedDescription": "",

            "sizeFt": "",
            "sizeAc": "",

            "postalCode": postal_code,

            "brochureUrl": [
                nu for u in raw_brochures
                if (nu := self.normalize_url(u))
            ],


            "agentCompanyName": "Gregory Moore Property",

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

    def _clean(self, val):
        return val.strip() if val else ""
    
    def extract_postcode(self, text):
        if not text:
            return ""

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        text = text.upper()
        m = re.search(FULL, text) or re.search(PARTIAL, text)
        return m.group().strip() if m else ""
    
    def normalize_url(self, url):
        if not url:
            return ""
        return urljoin("https://www.gregorymooreproperty.co.uk/", url)


