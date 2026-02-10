import re
import requests
from urllib.parse import urljoin
from lxml import html


class HarrocksCommercialPropertyScraper:
    BASE_URL = "https://harrocks.co.uk/properties/"
    DOMAIN = "https://harrocks.co.uk/"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }

    def __init__(self):
        self.results = []

    # -------------------------------------------------
    # RUN
    # -------------------------------------------------

    def run(self):
        resp = requests.get(self.BASE_URL, headers=self.HEADERS, timeout=30)
        resp.raise_for_status()

        tree = html.fromstring(resp.text)

        # Keep this exactly as-is (working correctly)
        listing_urls = tree.xpath(
            "//article[contains(@class,'et_pb_post') "
            "and not(.//*[contains(translate(text(),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'SOLD')])]"
            "//h2[contains(@class,'entry-title')]/a/@href"
        )

        listing_images = tree.xpath(
            "//article[contains(@class,'et_pb_post') "
            "and not(.//*[contains(translate(text(),'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'SOLD')])]"
            "//div[contains(@class,'et_pb_image_container')]//img/@src"
        )

        for url, img in zip(listing_urls, listing_images):
            try:
                data = self.parse_listing(urljoin(self.DOMAIN, url), img)
                self.results.append(data)
            except Exception:
                continue

        return self.results

    # -------------------------------------------------
    # LISTING DETAIL
    # -------------------------------------------------

    def parse_listing(self, url, image_url):
        resp = requests.get(url, headers=self.HEADERS, timeout=30)
        resp.raise_for_status()

        tree = html.fromstring(resp.text)

        display_address = self.clean(
            " ".join(tree.xpath("//div[contains(@class,'et_pb_text_inner')]/h1/text()"))
        )

        detailed_description = self.clean(
            " ".join(tree.xpath("//div[contains(@class,'et_pb_text_inner')]/p//text()"))
        )

        # Size from description (ft + ac)
        size_ft, size_ac = self.extract_size(detailed_description)

        #  Postcode ONLY from display address
        postal_code = self.extract_postcode(display_address)

        brochure_url = [
                nu for u in tree.xpath(
                    "//div[contains(@class,'et_pb_button_module_wrapper')]"
                    "//a[contains(@href,'.pdf')]/@href"
                )
                if (nu := self.normalize_url(u))
            ]


        #  Normalised sale type
        sale_type = self.extract_sale_type(tree)

        #  Tenure from description
        tenure = self.extract_tenure(detailed_description)

        return {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": "",
            "propertySubType": "",
            "propertyImage": [self.normalize_url(image_url)],
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": postal_code,
            "brochureUrl": brochure_url,
            "agentCompanyName": "Harrocks Commercial Property",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }

    # -------------------------------------------------
    # HELPERS
    # -------------------------------------------------

    def extract_sale_type(self, tree):
        """
        Only return:
        - For Sale
        - To Let
        """
        text = " ".join(tree.xpath("//h3//text()")).upper()

        if "FOR SALE" in text or 'SALE' in text:
            return "For Sale"

        if "TO LET" in text:
            return "To Let"

        return ""

    def extract_tenure(self, text):
        if not text:
            return ""

        t = text.lower()

        if "freehold" in t:
            return "Freehold"

        if "leasehold" in t or "lease" in t:
            return "Leasehold"

        return ""

    def extract_size(self, text):
        if not text:
            return "", ""

        raw = text.lower().replace(",", "")

        size_ft = ""
        size_ac = ""

        m = re.search(r'(\d+(?:\.\d+)?)\s*(sq\s*ft|sqft|sf)', raw)
        if m:
            size_ft = m.group(1)

        m = re.search(r'(\d+(?:\.\d+)?)\s*(acres?|ac)', raw)
        if m:
            size_ac = m.group(1)

        return size_ft, size_ac

    def extract_postcode(self, text):
        if not text:
            return ""

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        text = text.upper()
        m = re.search(FULL, text) or re.search(PARTIAL, text)
        return m.group() if m else ""

    def normalize_url(self, urls):
        if not urls:
            return ""
        return urljoin(self.DOMAIN, urls[0] if isinstance(urls, list) else urls)

    def clean(self, val):
        return val.strip() if val else ""
