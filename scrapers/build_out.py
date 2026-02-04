import requests
from lxml import html
import re
from utils import store_data_to_csv

CSV_FILE_NAME="data/data.csv"

class BuildOutScraper:
    BASE_URL = (
        "https://buildout.nmrk.com/plugins/"
        "267fecb3c0aa79175cdde4a3ab3e74e9403a90bd/inventory"
    )

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
        self.results = []


    def run(self):
        page = 0

        while True:
            url = self._build_page_url(page)
            response = requests.get(url, headers=self.HEADERS, timeout=30)

            if response.status_code != 200:
                break

            data = response.json()
            items = data.get("inventory", [])

            if not items:
                break

            for item in items:
                self.results.append(self.parse_item(item))

            page += 1

        if self.results:
            store_data_to_csv(self.results,CSV_FILE_NAME)


        return self.results


    def parse_item(self, item):
        description = self.get_detailed_description(item.get("show_link"))
        size_ft = self.extract_size_ft_from_text(item, description)
        obj = {
            "listingUrl": item.get("show_link"),
            "displayAddress": self._clean(item.get("address_one_line") or " ".join(item.get("address_three_line", [])) or item.get("display_name")),
            "price": self.get_price(item),
            "propertySubType": self._clean(item.get("property_sub_type_name")),
            "propertyImage": self.get_property_images(item),
            "detailedDescription": description,
            "sizeFt": size_ft,
            "sizeAc": self.get_size_ac(size_ft, description),
            "postalCode": self.get_postcode(item),
            "brochureUrl": self._clean(item.get("pdf_url")),
            "agentCompanyName": "Gerald Eve",
            "agentName": self.get_agent_name(item),
            "agentCity": "",
            "agentEmail": self.get_agent_email(item),
            "agentPhone": self.get_agent_phone(item),
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": "Freehold" if item.get("sale") else "Leasehold",
            "saleType": "For Sale" if item.get("sale") else "To Let",
        }
        return obj
    

    def _build_page_url(self, page):
        return f"{self.BASE_URL}?page={page}&light_view=true"

    def _clean(self, value):
        return value.strip() if value else ""
    
    def get_price(self, item):
        if not item.get("sale"):
            return ""
        for label, value in item.get("index_attributes", []):
            if label.lower() == "price":
                return self.extract_numeric_price(value)
        return None
    
    def extract_numeric_price(self, text):
        if not text:
            return None

        raw = str(text).lower()

        if any(p in raw for p in [
            "subject to offer",
            "price on application",
            "poa",
            "upon application",
            "on application",
        ]):
            return None

        raw = raw.replace(",", "")
        raw = re.sub(r"(to|upto|–|—)", "-", raw)

        numbers = re.findall(r"\d+", raw)
        if not numbers:
            return None

        return min(int(n) for n in numbers)
    
    def get_detailed_description(self, public_url):
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

            resp = requests.get(
                iframe_url,
                headers=self.HEADERS,
                timeout=30
            )

            if resp.status_code != 200:
                return ""

            tree = html.fromstring(resp.text)

            # 🔹 Main description
            description_texts = tree.xpath(
                "//div[@slug='description_custom_text']"
                "//p[@slug='description_description_value']//text()"
            )

            # 🔹 Location description
            location_texts = tree.xpath(
                "//div[@slug='location_description_custom_text']"
                "//p[@slug='location_description_location_description_value']//text()"
            )

            # 🔹 Highlights
            highlight_texts = tree.xpath(
                "//div[@slug='highlights_custom_text']//li//text()"
            )

            description = " ".join(t.strip() for t in description_texts if t.strip())
            location_description = " ".join(
                t.strip() for t in location_texts if t.strip()
            )
            highlights = " ".join(
                t.strip() for t in highlight_texts if t.strip()
            )

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
        
    def get_size_ac(self, size_ft, description):

        # 1️⃣ Convert from sizeFt if available
        if size_ft:
            return round(size_ft / 43560, 3)

        # 2️⃣ Otherwise, extract directly from text
        return self.extract_size_ac_from_text(description)

        
    def extract_size_ac_from_text(self, text):
        if not text:
            return None

        text = text.lower().replace(",", "")

        pattern = r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|ac)'

        matches = re.findall(pattern, text)
        if not matches:
            return None

        values = []
        for m in matches:
            start = float(m[0])
            end = float(m[1]) if m[1] else None
            values.append(start if not end else min(start, end))

        return min(values) if values else None
    
    def extract_size_ft_from_text(self, item, text):
        size_summary = item.get("size_summary")

        # 1️⃣ Try size_summary (numeric OR unit-based)
        if size_summary is not None:
            raw = str(size_summary).replace(",", "").strip()
            if raw.isdigit():
                return int(raw)

        size_ft = self._extract_sqft_with_units(size_summary)
        if size_ft:
            return size_ft

        # 2️⃣ Fallback to description text
        return self._extract_sqft_with_units(text)
    
    def _extract_sqft_with_units(self, text):
        if not text:
            return None

        text = str(text).lower().replace(",", "")
        values_sqft = []

        # ---------- SQ FT ----------
        sqft_pattern = r'\b(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\.?\s*ft\.?|sqft|square\s*feet|sf|s\.?f\.?)\b'
        for start, end, _ in re.findall(sqft_pattern, text):
            start = float(start)
            end = float(end) if end else None
            values_sqft.append(start if not end else min(start, end))

        # ---------- SQ METERS ----------
        sqm_pattern = r'\b(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sqm|sq\.?\s*m\.?|m²|m2|square\s*met(?:er|re)s)\b'
        for start, end, _ in re.findall(sqm_pattern, text):
            start = float(start) * 10.7639
            end = float(end) * 10.7639 if end else None
            values_sqft.append(start if not end else min(start, end))

        # ---------- HECTARES (MUST COME BEFORE ACRES) ----------
        hectare_pattern = r'\b(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(hectares?|ha|ha\.?)\b'
        for start, end, _ in re.findall(hectare_pattern, text):
            start = float(start) * 107639
            end = float(end) * 107639 if end else None
            values_sqft.append(start if not end else min(start, end))

        # ---------- ACRES ----------
        acre_pattern = r'\b(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac)\b'
        for start, end, _ in re.findall(acre_pattern, text):
            start = float(start) * 43560
            end = float(end) * 43560 if end else None
            values_sqft.append(start if not end else min(start, end))

        return int(min(values_sqft)) if values_sqft else None

    def get_property_images(self, item):
        return [
            url for url in [
                item.get("photo_url"),
                item.get("large_thumbnail_url"),
            ] if url
        ]

    def get_agent_name(self, item):
        agents = item.get("broker_contacts", [])
        return agents[0].get("name", "") if agents else ""

    def get_agent_email(self, item):
        agents = item.get("broker_contacts", [])
        return agents[0].get("email", "").lower() if agents else ""

    def get_agent_phone(self, item):
        agents = item.get("broker_contacts", [])
        return agents[0].get("phone", "") if agents else ""

    def get_postcode(self, item):
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
        Extract UK postcode from any text.
        Supports FULL and PARTIAL postcodes.
        """
        if not text:
            return ""

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        text = text.upper()

        match = re.search(FULL, text) or re.search(PARTIAL, text)
        if match:
            return match.group().upper().strip()

        return ""

    def extract_numeric(self, text):
        nums = re.findall(r"\d+", str(text).replace(",", ""))
        return int(nums[0]) if nums else None
