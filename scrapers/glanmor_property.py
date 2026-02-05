import requests
import re
from lxml import html
from utils import store_data_to_csv

class GlanmorPropertyScraper:
    BASE_SEARCH = "https://glanmorproperty.co.uk/search-results/"

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/144.0.0.0 Safari/537.36"
        )
    }

    def __init__(self):
        self.results = []

    def run(self):
        page = 1

        while True:

            url = self._build_page_url(page)

            resp = requests.get(url, headers=self.HEADERS, timeout=30)
            if resp.status_code != 200:
                break

            tree = html.fromstring(resp.text)
            listing_urls = tree.xpath(
                "//div[contains(@class,'item-listing-wrap')]//h2[@class='item-title']/a/@href"
            )

            if not listing_urls:
                break

            for link in listing_urls:
                try:
                    self.results.append(self.parse_listing(link))
                except Exception:
                    continue

            page += 1
            if page==2: 
                break

        return self.results

    def _build_page_url(self, page):
        if page == 1:
            return self.BASE_SEARCH
        return f"{self.BASE_SEARCH}page/{page}/"

    def parse_listing(self, url):
        resp = requests.get(url, headers=self.HEADERS, timeout=30)
        tree = html.fromstring(resp.text)

        size_ft, size_ac = self.extract_size(tree)


        title = self._clean(" ".join(tree.xpath(
            "//div[contains(@class,'property-title-price-wrap')]//div[@class='page-title']/h1/text()[normalize-space()]"
        )))


        address = self._clean(" ".join(tree.xpath(
            "//div[@class='container']/address[@class='item-address']/text()[normalize-space()]"
        )))

        sale_type = self._clean(" ".join(tree.xpath(
            "//li[strong[text()='Property Status:']]/span/text()"
        )))

        obj = {
            "listingUrl": url,
            "displayAddress": address,
            "price": self.get_price(tree, sale_type),
            "propertySubType": self._clean(" ".join(tree.xpath(
                "//li[normalize-space()='Property Type']/preceding-sibling::li[1]/strong/text()"
            ))),
            "propertyImage": self.get_property_images(tree),#need to check
            "detailedDescription": self.get_description(tree),
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(address) if address else self.extract_postcode(title),
            "brochureUrl": self._clean(" ".join(tree.xpath(
                "//div[contains(@class,'property-documents')]//a/@href"
            ))),
            "agentCompanyName": "Glanmor Property",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": self.get_tenure(tree),
            "saleType": "For Sale" if "sale" in sale_type.lower() else "To Let",
        }
        return obj

    # ------------- helpers ------------ #

    def get_price(self, tree, sale_type):
        if "rent" in sale_type.lower():
            return ""

        text = self._clean(" ".join(tree.xpath(
            "//li[@class='item-price item-price-text price-single-listing-text']/text()"
        )))

        return self.extract_numeric_price(text)
    
    def get_property_images(self, tree):
        """
        Extract all gallery images.
        Supports lazy-loaded images (data-src / data-lazy).
        Returns a list of unique image URLs.
        """
        images = tree.xpath("//div[@id='property-gallery-js']//img")

        urls = []
        for img in images:
            url = (
                img.get("src")
                or img.get("data-src")
                or img.get("data-lazy")
            )

            if url and url not in urls:
                urls.append(url)

        return urls


    def get_description(self, tree):
        texts = tree.xpath(
            "//div[@class='block-content-wrap']/p[not(ancestor::div[contains(@class,'property-documents')])]//text()"
        )
        return " ".join(t.strip() for t in texts if t.strip())
    



    def get_tenure(self, tree):
        text = " ".join(tree.xpath("//p//text()")).lower()
        if "freehold" in text:
            return "Freehold"
        elif "leasehold" in text:
            return "Leasehold"
        return ""

    def _clean(self, val):
        return val.strip() if val else ""

    def extract_postcode(self, text):
        """
        Extract UK postcode (FULL or PARTIAL)
        """
        if not text:
            return ""

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        text = text.upper()
        match = re.search(FULL, text) or re.search(PARTIAL, text)

        return match.group().upper().strip() if match else ""


    def extract_numeric_price(self , text):
        """
        Convert any price text to a numeric value.

        Handles:
        - POA / On Application / Subject to Offer
        - Price ranges (returns minimum)
        - Comma-separated values
        - Currency symbols (£, $, €)
        - Per annum / pcm / pw text noise

        Returns:
        - int (minimum price)
        - "" if price is not explicitly provided
        """

        if not text:
            return ""

        raw = str(text).lower()

        # -------- ignore non-priced listings --------
        ignore_phrases = [
            "subject to offer",
            "price on application",
            "upon application",
            "on application",
            "poa",
            "tbc",
            "ask agent",
        ]

        if any(p in raw for p in ignore_phrases):
            return ""

        # -------- normalize text --------
        raw = raw.replace(",", "")
        raw = raw.replace("£", "").replace("$", "").replace("€", "")
        raw = re.sub(r"(per annum|pa|p\.a\.|pcm|pw|per week|per month)", "", raw)

        # normalize ranges: to / – / —
        raw = re.sub(r"(to|upto|–|—)", "-", raw)

        # -------- extract numbers --------
        numbers = re.findall(r"\d+", raw)
        if not numbers:
            return ""

        # return minimum if range
        return min(int(n) for n in numbers)
    
    
    def extract_size(self, tree):
        """
        If both Property Size and Land Area exist:
        → return BOTH sizeFt and sizeAc
        """

        text = " ".join(tree.xpath(
            "//li[.//strong[contains(text(),'Property Size') or contains(text(),'Land Area')]]//span/text()"
        ))

        if not text:
            return "", ""

        text = (
            text.lower()
            .replace(",", "")
            .replace("m²", "m2")
            .replace("㎡", "m2")
        )

        size_ft = ""
        size_ac = ""

        # ---------- SQ FT ----------
        sqft_pattern = (
            r'\b(\d+(?:\.\d+)?)'
            r'(?:\s*(?:-|to)\s*(\d+(?:\.\d+)?))?'
            r'\s*(sq\.?\s*ft|sqft|sf)\b'
        )
        m = re.search(sqft_pattern, text)
        if m:
            start = float(m.group(1))
            end = float(m.group(2)) if m.group(2) else ""
            size_ft = int(min(start, end)) if end else int(start)

        # ---------- SQ METERS → SQ FT ----------
        sqm_pattern = (
            r'\b(\d+(?:\.\d+)?)'
            r'(?:\s*(?:-|to)\s*(\d+(?:\.\d+)?))?'
            r'\s*(sqm|m2|square\s*met(?:er|re)s)\b'
        )
        m = re.search(sqm_pattern, text)
        if m and size_ft == "":
            start = float(m.group(1)) * 10.7639
            end = float(m.group(2)) * 10.7639 if m.group(2) else ""
            size_ft = int(min(start, end)) if end else int(start)

        # ---------- ACRES ----------
        acre_pattern = (
            r'\b(\d+(?:\.\d+)?)'
            r'(?:\s*(?:-|to)\s*(\d+(?:\.\d+)?))?'
            r'\s*(acres?|acre|ac)\b'
        )
        m = re.search(acre_pattern, text)
        if m:
            start = float(m.group(1))
            end = float(m.group(2)) if m.group(2) else ""
            size_ac = round(min(start, end) if end else start, 3)

        # ---------- HECTARES → ACRES ----------
        hectare_pattern = (
            r'\b(\d+(?:\.\d+)?)'
            r'(?:\s*(?:-|to)\s*(\d+(?:\.\d+)?))?'
            r'\s*(hectares?|ha)\b'
        )
        m = re.search(hectare_pattern, text)
        if m and size_ac == "":
            start = float(m.group(1)) * 2.47105
            end = float(m.group(2)) * 2.47105 if m.group(2) else ""
            size_ac = round(min(start, end) if end else start, 3)

        return size_ft, size_ac
