import requests
import re
from lxml import html


class GoldenbergRealEstateScraper:
    BASE_URL = "https://www.goldenberg.co.uk/"

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
            "//section[@id='for-sale1']"
            "//div[contains(@class,'large-6') and contains(@class,'medium-6')]"
            "[not(.//div[contains(@class,'soldsign')])]"
        )

        for el in listings:
            try:
                self.results.append(self.parse_listing(el))
            except Exception:
                continue

        return self.results

    # ---------------- LISTING ---------------- #

    def parse_listing(self, el):
        description = self._clean(" ".join(el.xpath(
            ".//div[contains(@class,'tabs-panel') and contains(@id,'panel1')]/p//text()"
        )))

        size_ft = self.extract_sqft(description)
        address = self.extract_address(el)

        obj = {
            "listingUrl": self._clean(" ".join(el.xpath(
                ".//a[contains(@href,'.pdf')]/@href"
            ))), #brouchre url is the listing url here because all property info exists on same page

           "displayAddress": address, #because no where address is given , only map is showing

            "price": self.extract_numeric_price(description),

            "propertySubType": "",

            "propertyImage": el.xpath(
                ".//div[@class='featured-item']//img/@src"
            ),

            "detailedDescription": description,

            "sizeFt": size_ft,
            "sizeAc": "",

            "postalCode": self.extract_postcode(address),


            "brochureUrl": [
                self._clean(u) for u in el.xpath(
                    ".//a[contains(@href,'.pdf')]/@href"
                ) if self._clean(u)
            ],

            "agentCompanyName": "Goldenberg Real Estate",

            "agentName": "",

            "agentCity": "",

            "agentEmail":"",

            "agentPhone":"",

            "agentStreet": "",
            "agentPostcode": "",

            "tenure": self.get_tenure(description),

            "saleType": self.get_sale_type(description),
        }

        return obj

    # ---------------- HELPERS ---------------- #



    def extract_address(self, el):
        """
        Extracts display address from featured item title
        """
        address = el.xpath(
            ".//div[contains(@class,'featured-item-hover')]//h3/text()"
        )

        return self._clean(address[0]) if address else ""
    

    def extract_sqft(self, text):
        if not text:
            return ""
        text = text.lower().replace(",", "")
        m = re.search(r'(\d+(?:\.\d+)?)\s*sq\s*ft', text)
        return int(float(m.group(1))) if m else ""


    def extract_numeric_price(self, text):
        """
        Rules:
        - Ignore p.a. / rent
        - Ignore per sq ft / per sqm / dimension-based prices
        - If range -> return minimum
        - If single price -> return it
        """

        if not text:
            return ""

        raw = text.lower()

        # Ignore POA-type listings
        if any(x in raw for x in [
            "price on application",
            "poa",
            "upon application",
            "on application",
        ]):
            return ""

        # Normalize
        raw = raw.replace(",", "")

        prices = []

        # Find all £ numbers with context
        for match in re.finditer(r"£\s*(\d+)", raw):
            value = int(match.group(1))

            # Get surrounding context (important)
            start, end = match.span()
            context = raw[max(0, start - 30): min(len(raw), end + 30)]

            #  Exclude rent
            if any(x in context for x in ["p.a", "per annum", "pa"]):
                continue

            #  Exclude per-area / dimension prices
            if any(x in context for x in [
                "per sq",
                "sq ft",
                "sqft",
                "psf",
                "sqm",
                "m²",
                "m2",
            ]):
                continue

            prices.append(value)

        # If multiple prices (range), return minimum
        return min(prices) if prices else ""


    def get_tenure(self, text):
        if not text:
            return ""

        t = text.lower()

        if "freehold" in t:
            return "Freehold"

        if "leasehold" in t or "lease" in t:
            return "Leasehold"

        return ""

    def get_sale_type(self, text):
        t = text.lower()
        if "for sale" in t or "sale" in t:
            return "For Sale"
        if "to let" in t:
            return "To Let"
        return ""

    def extract_postcode(self, text):
        if not text:
            return ""
        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'
        text = text.upper()
        m = re.search(FULL, text) or re.search(PARTIAL, text)
        return m.group().strip() if m else ""

    def _clean(self, val):
        return val.strip() if val else ""
