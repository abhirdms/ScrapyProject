import re
import requests
from urllib.parse import urljoin
from lxml import html


class PantherSecuritiesScraper:
    SEARCH_URL  = "https://pantherplc.com/property-grid-view/"
    FOR_SALE_URL = "https://pantherplc.com/investment-opportunity/properties-for-sale/"
    DOMAIN      = "https://pantherplc.com"

    CATEGORIES = [
        "industrial",
        "warehouse",
        "land",
        "leisure",
        "offices",
        "redevelopment-site",
        "residential",
        "retail",
        "roadsidetrade-counter-opportunity",
    ]

    HEADERS = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "accept-language": "en-US,en;q=0.9",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://pantherplc.com",
        "referer": "https://pantherplc.com/properties/",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36"
        ),
    }

    def __init__(self):
        self.results = []
        self.seen_addresses = set()
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    # ===================== RUN ===================== #

    def run(self):
        # Scrape all To Let categories
        for category in self.CATEGORIES:
            try:
                self._scrape_category(category)
            except Exception as e:
                continue

        # Scrape the investment / For Sale page
        try:
            self._scrape_for_sale()
        except Exception:
            pass

        return self.results

    # ===================== SCRAPE FOR SALE PAGE ===================== #

    def _scrape_for_sale(self):
        resp = self.session.get(self.FOR_SALE_URL)
        resp.raise_for_status()

        tree = html.fromstring(resp.content)
        items = tree.xpath("//div[contains(@class,'property-grid-item')]")

        if not items:
            return

        self._parse_items(items, force_sale_type="For Sale")

    # ===================== SCRAPE ONE CATEGORY ===================== #

    def _scrape_category(self, category):
        post_data = {
            "property-category": category,
            "region": "All",
        }
        resp = self.session.post(self.SEARCH_URL, data=post_data)
        resp.raise_for_status()

        tree = html.fromstring(resp.content)
        items = tree.xpath("//div[contains(@class,'property-grid-item')]")

        if not items:
            return

        self._parse_items(items)

    # ===================== PARSE ITEMS ===================== #

    def _parse_items(self, items, force_sale_type=None):
        for item in items:
            try:
                obj = self.parse_item(item, force_sale_type=force_sale_type)
                if not obj:
                    continue

                # Deduplicate by display address
                addr_key = obj["displayAddress"].upper().strip()
                if addr_key in self.seen_addresses:
                    continue
                self.seen_addresses.add(addr_key)

                self.results.append(obj)

            except Exception:
                continue

    # ===================== ITEM PARSER ===================== #

    def parse_item(self, item, force_sale_type=None):
        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(
            " ".join(item.xpath(".//h1/text()"))
        )

        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type = self._clean(
            " ".join(item.xpath(".//p[b[contains(text(),'Usage')]]/text()"))
        ).strip()

        # ---------- SIZE RAW ---------- #
        size_raw = self._clean(
            " ".join(item.xpath(".//p[b[contains(text(),'Size')]]/text()"))
        )
        size_ft, size_ac = self.extract_size(size_raw)

        # ---------- RENT / PRICE RAW ---------- #
        # Covers: Rent, Price, Asking Price, Sale Price
        rent_raw = self._clean(
            " ".join(item.xpath(
                ".//p[b[contains(text(),'Rent') or contains(text(),'Price') or contains(text(),'Sale')]]/text()"
            ))
        )

        # ---------- DETAILED DESCRIPTION ---------- #
        desc_parts = item.xpath(
            ".//div[contains(@class,'grid-text-container')]"
            "/p[not(b) and not(@class)]//text()"
        )
        detailed_description = self._clean(" ".join(desc_parts))

        full_text = f"{rent_raw} {detailed_description}".strip()

        # ---------- SALE TYPE ---------- #
        if force_sale_type:
            sale_type = force_sale_type
        else:
            sale_type = self.extract_sale_type(rent_raw + " " + detailed_description)

        # ---------- PRICE (only For Sale) ---------- #
        price = self.extract_numeric_price(rent_raw, sale_type)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- POSTCODE ---------- #
        postcode = self.extract_postcode(display_address)

        # ---------- IMAGES ---------- #
        property_images = list(dict.fromkeys(
            src for src in item.xpath(
                ".//div[contains(@class,'grid-image-container')]//img/@src"
            ) if src
        ))

        # ---------- BROCHURE / LISTING URL ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in item.xpath(".//a[contains(text(),'PDF Brochure')]/@href")
        ]
        listing_url = brochure_urls[0] if brochure_urls else ""

        # ---------- AGENT CONTACT ---------- #
        # Contact text may be bare text in div OR wrapped in <p>
        contact_text = self._clean(
            " ".join(
                item.xpath(".//div[contains(@class,'contactDetails')]//text()")
            )
        )
        agent_name, agent_phone = self.extract_contact(contact_text)

        obj = {
            "listingUrl": listing_url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": full_text,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": postcode,
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Panther Securities",
            "agentName": agent_name,
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": agent_phone,
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }
        return obj

    # ===================== HELPERS ===================== #

    def extract_contact(self, text):
        if not text:
            return "", ""

        phone_match = re.search(r'(\d[\d\s]{9,})', text)
        phone = phone_match.group(1).strip() if phone_match else ""

        name_match = re.search(
            r'contact\s+([A-Z][a-z\-]+(?:\s+[A-Z][a-z\-]+)+)',
            text
        )
        name = name_match.group(1).strip() if name_match else ""

        return name, phone

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower()
        text = text.replace(",", "")
        text = text.replace("ft\u00b2", "sq ft")
        text = text.replace("m\u00b2", "sqm")
        text = re.sub(r"[\u2013\u2014\u2212]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*feet)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        if not size_ft:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(sqm|sq\.?\s*m|m2|square\s*metres|square\s*meters)',
                text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm_value = min(a, b) if b else a
                size_ft = round(sqm_value * 10.7639, 3)

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac\.?)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        if not size_ac:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(hectares?|ha)',
                text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                hectare_value = min(a, b) if b else a
                size_ac = round(hectare_value * 2.47105, 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale":
            return ""
        if not text:
            return ""

        t = text.lower()

        if any(k in t for k in [
            "poa", "price on application", "upon application", "on application"
        ]):
            return ""

        if any(k in t for k in [
            "per annum", "pax", " pa", "per year", "pcm",
            "per month", " pw", "per week", "rent"
        ]):
            return ""

        m = re.search(
            r'(?:\u00a3|\u20ac|\$)\s*(\d+(?:,\d{3})*(?:\.\d+)?)(\s*[mk])?',
            t
        )
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))
        suffix = (m.group(2) or "").strip().lower()
        if suffix == "m":
            num *= 1_000_000
        if suffix == "k":
            num *= 1_000

        return str(int(num))

    def extract_tenure(self, text):
        if not text:
            return ""
        t = text.lower()
        if "freehold" in t:
            return "Freehold"
        if "leasehold" in t:
            return "Leasehold"
        return ""

    def extract_sale_type(self, text):
        if not text:
            return ""
        t = text.lower()
        if "for sale" in t or "sale price" in t or "asking price" in t:
            return "For Sale"
        if "to let" in t or "rent" in t or "per annum" in t or "pax" in t or " pa" in t:
            return "To Let"
        return ""

    def extract_postcode(self, text):
        if not text:
            return ""
        text = text.upper()
        full_pattern = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        partial_pattern = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'
        match = re.search(full_pattern, text)
        if match:
            return match.group().strip()
        match = re.search(partial_pattern, text)
        return match.group().strip() if match else ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""


if __name__ == "__main__":
    scraper = PantherSecuritiesScraper()
    results = scraper.run()