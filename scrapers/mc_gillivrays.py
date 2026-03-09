import re
import requests
from urllib.parse import urljoin
from lxml import html


class McGillivraysScraper:
    BASE_URL = "https://www.mcgillivrays.com/properties.aspx"
    DOMAIN = "https://www.mcgillivrays.com"

    HEADERS = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-US,en;q=0.9,fr;q=0.8",
        "cache-control": "max-age=0",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://www.mcgillivrays.com",
        "referer": "https://www.mcgillivrays.com/properties.aspx",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    }

    def __init__(self):
        self.results = []
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    # ===================== RUN ===================== #

    def run(self):
        # Step 1: GET the page to retrieve a fresh __VIEWSTATE
        get_resp = self.session.get(self.BASE_URL)
        get_resp.raise_for_status()
        tree = html.fromstring(get_resp.content)

        viewstate = self._get_input_value(tree, "__VIEWSTATE")
        viewstate_generator = self._get_input_value(tree, "__VIEWSTATEGENERATOR")

        # Step 2: POST with search parameters (all properties, no filters)
        post_data = {
            "__EVENTTARGET": "",
            "__EVENTARGUMENT": "",
            "__LASTFOCUS": "",
            "__VIEWSTATE": viewstate,
            "__VIEWSTATEGENERATOR": viewstate_generator,
            "ddlLocation": "0",
            "rblMeasurement": "Sq ft",
            "ddlSqFt": "1",
            "btnSearch.x": "74",
            "btnSearch.y": "8",
        }

        post_resp = self.session.post(self.BASE_URL, data=post_data)
        post_resp.raise_for_status()

        tree = html.fromstring(post_resp.content)
        property_items = tree.xpath("//div[contains(@class,'property-item')]")

        for item in property_items:
            try:
                obj = self.parse_listing(item)
                if obj:
                    self.results.append(obj)

            except Exception:
                continue

        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, item):
        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(
            " ".join(item.xpath(".//h3/text()"))
        )

        # ---------- SIZE ---------- #
        size_raw = self._clean(
            " ".join(item.xpath(".//p[@class='size']/text()"))
        )
        size_ft, size_ac = self.extract_size(size_raw)

        # ---------- DETAILED DESCRIPTION ---------- #
        # Grab all paragraph text inside property-info, excluding the size paragraph
        detailed_description = self._clean(
            " ".join(
                item.xpath(
                    ".//div[@class='property-info']//p[not(@class='size')]//text()"
                )
            )
        )

        # ---------- SALE TYPE ---------- #
        sale_type = self.extract_sale_type(detailed_description)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(detailed_description, sale_type)

        # ---------- POSTCODE ---------- #
        postcode = self.extract_postcode(display_address)

        # ---------- LINKS (particulars / EPC / enquire) ---------- #
        particulars_links = [
            urljoin(self.DOMAIN, href)
            for href in item.xpath(".//a[contains(text(),'Particulars')]/@href")
        ]
        brochure_urls = particulars_links  # Particulars PDFs serve as brochures

        # ---------- PROPERTY IMAGE ---------- #
        property_images = [
            urljoin(self.DOMAIN, src)
            for src in item.xpath(".//img/@src")
            if src and "media/images" in src
        ]

        # ---------- LISTING URL ---------- #
        # McGillivrays uses PDF particulars rather than individual listing pages;
        # use the particulars PDF URL as the listing URL if available.
        listing_url = particulars_links[0] if particulars_links else self.BASE_URL

        obj = {
            "listingUrl": listing_url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": postcode,
            "brochureUrl": brochure_urls,
            "agentCompanyName": "McGillivrays",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }
        return obj

    # ===================== HELPERS ===================== #

    def _get_input_value(self, tree, name):
        vals = tree.xpath(f"//input[@name='{name}']/@value")
        return vals[0] if vals else ""

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower()
        text = text.replace(",", "")
        text = text.replace("ft²", "sq ft")
        text = text.replace("m²", "sqm")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        # Square feet
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*feet)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        # Square metres → sqft
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

        # Acres
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac\.?)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        # Hectares → acres
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
            "per annum", " pa", "per year", "pcm",
            "per month", " pw", "per week", "rent"
        ]):
            return ""

        m = re.search(
            r'(?:£|€|\$)\s*(\d+(?:,\d{3})*(?:\.\d+)?)(\s*[mk])?',
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
        if "for sale" in t or "investment" in t:
            return "For Sale"
        if "to let" in t or "rent" in t or "per annum" in t or " pa" in t:
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

    def normalize_sale_type(self, text):
        t = text.lower()
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""


if __name__ == "__main__":
    scraper = McGillivraysScraper()
    results = scraper.run()