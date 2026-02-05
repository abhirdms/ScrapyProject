import requests
from lxml import html
import re
from utils import store_data_to_csv



class BuildOutScraper:
    # Base inventory API endpoint
    BASE_URL = (
        "https://buildout.nmrk.com/plugins/"
        "267fecb3c0aa79175cdde4a3ab3e74e9403a90bd/inventory"
    )

    # Standard headers to mimic browser-based AJAX requests
    HEADERS = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/144.0.0.0 Safari/537.36"
        ),
    }

    def __init__(self):
        # Stores parsed listing dictionaries
        self.results = []

    def run(self):
        """
        Main runner:
        - Iterates through paginated inventory
        - Parses each listing
        - Stores final results into CSV
        """
        page = 0

        while True:
            url = self._build_page_url(page)
            response = requests.get(url, headers=self.HEADERS, timeout=30)

            # Stop if API fails
            if response.status_code != 200:
                break

            data = response.json()
            items = data.get("inventory", [])

            # Stop if no more inventory
            if not items:
                break

            for item in items:
                self.results.append(self.parse_item(item))

            page += 1

  
        return self.results

    def parse_item(self, item):
        """
        Maps raw API item to final structured output fields
        according to provided context
        """
        description = self.get_detailed_description(item.get("show_link"))

        # Extract size in square feet (numeric)
        size_ft, size_ac = self.extract_size(item, description)

        obj = {
            # listingUrl: link to the property
            "listingUrl": item.get("show_link"),

            # displayAddress: full property address
            "displayAddress": self._clean(
                item.get("address_one_line")
                or " ".join(item.get("address_three_line", []))
                or item.get("display_name")
            ),

            # price: numeric, only if property is for sale (minimum if range)
            "price": self.get_price(item),

            # propertySubType: office / retail / industrial etc.
            "propertySubType": self._clean(item.get("property_sub_type_name")),

            # propertyImage: list of image URLs
            "propertyImage": self.get_property_images(item),

            # detailedDescription: full property description text
            "detailedDescription": description,

            # sizeFt: property size in square feet
            "sizeFt": size_ft,
            "sizeAc": size_ac,

            # postalCode: UK postcode extracted from multiple sources
            "postalCode": self.get_postcode(item),

            # brochureUrl: link to PDF brochure
            "brochureUrl": self._clean(item.get("pdf_url")),

            # agentCompanyName: fixed company name for this scraper
            "agentCompanyName": "Gerald Eve",

            # agentName: marketing agent name (person)
            "agentName": self.get_agent_name(item),

            # agentCity: not provided by source
            "agentCity": "",

            # agentEmail: marketing agent email
            "agentEmail": self.get_agent_email(item),

            # agentPhone: marketing agent phone
            "agentPhone": self.get_agent_phone(item),

            # agentStreet: not provided by source
            "agentStreet": "",

            # agentPostcode: not provided by source
            "agentPostcode": "",

            # tenure: Freehold if for sale else Leasehold
            "tenure": "Freehold" if item.get("sale") else "Leasehold",

            # saleType: For Sale / To Let (sale takes priority)
            "saleType": "For Sale" if item.get("sale") else "To Let",
        }

        return obj

    def _build_page_url(self, page):
        # Build paginated inventory URL
        return f"{self.BASE_URL}?page={page}&light_view=true"

    def _clean(self, value):
        # Safely strip string values
        return value.strip() if value else ""

    def get_price(self, item):
        """
        Extracts numeric price only if property is for sale.
        Returns minimum value if range is provided.
        """
        if not item.get("sale"):
            return ""

        for label, value in item.get("index_attributes", []):
            if label.lower() == "price":
                return self.extract_numeric_price(value)

        return ""

    def extract_numeric_price(self, text):
        """
        Handles:
        - POA / On Application
        - Price ranges
        - Comma-separated values
        """
        if not text:
            return ""

        raw = str(text).lower()

        if any(p in raw for p in [
            "subject to offer",
            "price on application",
            "poa",
            "upon application",
            "on application",
        ]):
            return ""

        raw = raw.replace(",", "")
        raw = re.sub(r"(to|upto|–|—)", "-", raw)

        numbers = re.findall(r"\d+", raw)
        if not numbers:
            return ""

        # Return minimum price if range
        return min(int(n) for n in numbers)

    def get_detailed_description(self, public_url):
        """
        Fetches detailed description by loading iframe page
        and extracting description, location, and highlights
        """
        if not public_url:
            return ""

        try:
            slug = public_url.rstrip("/").split("/")[-1]

            iframe_url = (
                "https://buildout.nmrk.com/plugins/"
                "267fecb3c0aa79175cdde4a3ab3e74e9403a90bd"
                "/www.nmrk.com/inventory/"
                f"{slug}"
                "?pluginId=0&iframe=true&embedded=true&cacheSearch=true"
            )

            resp = requests.get(iframe_url, headers=self.HEADERS, timeout=30)
            if resp.status_code != 200:
                return ""

            tree = html.fromstring(resp.text)

            # Main description text
            description_texts = tree.xpath(
                "//div[@slug='description_custom_text']"
                "//p[@slug='description_description_value']//text()"
            )

            # Location description text
            location_texts = tree.xpath(
                "//div[@slug='location_description_custom_text']"
                "//p[@slug='location_description_location_description_value']//text()"
            )

            # Property highlights list
            highlight_texts = tree.xpath(
                "//div[@slug='highlights_custom_text']//li//text()"
            )

            description = " ".join(t.strip() for t in description_texts if t.strip())
            location_description = " ".join(t.strip() for t in location_texts if t.strip())
            highlights = " ".join(t.strip() for t in highlight_texts if t.strip())

            parts = []
            if description:
                parts.append(description)
            if location_description:
                parts.append(f" Location: {location_description}")
            if highlights:
                parts.append(f" Highlights: {highlights}")

            return " ".join(parts)

        except Exception:
            return ""
    
    def extract_size(self, item, text):
        """
        Returns (sizeFt, sizeAc)
        Rules:
        - sq ft / sqm → sizeFt
        - acres / hectares → sizeAc
        """
        size_summary = item.get("size_summary")

        # 1️numeric-only fallback (assume sq ft)
        if size_summary and str(size_summary).strip().isdigit():
            return int(size_summary), ""

        # 2️combine all possible text
        combined_text = " ".join(
            t for t in [
                str(size_summary) if size_summary else "",
                str(text) if text else ""
            ] if t
        )

        # normalize text ONCE
        combined_text = (
            combined_text
            .replace("m²", "m2")
            .replace("㎡", "m2")
            .lower()
            .replace(",", "")
        )

        # ---------- SQ FT ----------
        sqft_pattern = (
            r'\b(\d+(?:\.\d+)?)'
            r'(?:\s*(?:-|to)\s*(\d+(?:\.\d+)?))?'
            r'\s*(sq\.?\s*ft|sqft|square\s*feet|sf)\b'
        )
        m = re.search(sqft_pattern, combined_text)
        if m:
            start = float(m.group(1))
            end = float(m.group(2)) if m.group(2) else ""
            return int(min(start, end)) if end else int(start), ""

        # ---------- SQ METERS → SQ FT ----------
        sqm_pattern = (
            r'\b(\d+(?:\.\d+)?)'
            r'(?:\s*(?:-|to)\s*(\d+(?:\.\d+)?))?'
            r'\s*(sqm|sq\.?\s*m|m2|square\s*met(?:er|re)s)\b'
        )
        m = re.search(sqm_pattern, combined_text)
        if m:
            start = float(m.group(1)) * 10.7639
            end = float(m.group(2)) * 10.7639 if m.group(2) else ""
            return int(min(start, end)) if end else int(start), ""

        # ---------- ACRES ----------
        acre_pattern = (
            r'\b(\d+(?:\.\d+)?)'
            r'(?:\s*(?:-|to)\s*(\d+(?:\.\d+)?))?'
            r'\s*(acres?|acre|ac)\b'
        )
        m = re.search(acre_pattern, combined_text)
        if m:
            start = float(m.group(1))
            end = float(m.group(2)) if m.group(2) else ""
            return "", round(min(start, end) if end else start, 3)

        # ---------- HECTARES → ACRES ----------
        hectare_pattern = (
            r'\b(\d+(?:\.\d+)?)'
            r'(?:\s*(?:-|to)\s*(\d+(?:\.\d+)?))?'
            r'\s*(hectares?|ha)\b'
        )
        m = re.search(hectare_pattern, combined_text)
        if m:
            start = float(m.group(1)) * 2.47105
            end = float(m.group(2)) * 2.47105 if m.group(2) else ""
            return "", round(min(start, end) if end else start, 3)


        return "", ""


    def get_property_images(self, item):
        # Returns list of available image URLs
        return [
            url for url in [
                item.get("photo_url"),
                item.get("large_thumbnail_url"),
            ] if url
        ]

    def get_agent_name(self, item):
        # Extract agent name if available
        agents = item.get("broker_contacts", [])
        return agents[0].get("name", "") if agents else ""

    def get_agent_email(self, item):
        # Extract agent email if available
        agents = item.get("broker_contacts", [])
        return agents[0].get("email", "").lower() if agents else ""

    def get_agent_phone(self, item):
        # Extract agent phone if available
        agents = item.get("broker_contacts", [])
        return agents[0].get("phone", "") if agents else ""

    def get_postcode(self, item):
        """
        Attempts postcode extraction from:
        - zip
        - address lines
        - display name
        - listing name
        """
        for source in [
            item.get("zip"),
            " ".join(item.get("address_three_line", [])),
            item.get("display_name"),
            item.get("name"),
        ]:
            code = self.extract_postcode(source)
            if code:
                return code
        return ""

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

    def extract_numeric(self, text):
        # Generic numeric extractor
        nums = re.findall(r"\d+", str(text).replace(",", ""))
        return int(nums[0]) if nums else ""
