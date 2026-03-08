import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class NJWEScraper:

    BASE_URL = "https://www.njwe.co.uk/properties.html"
    DOMAIN = "https://www.njwe.co.uk"

    def __init__(self):

        self.results = []

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        service = Service("/usr/bin/chromedriver")
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 20)

    # ===================== RUN ===================== #

    def run(self):

        self.driver.get(self.BASE_URL)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h2[contains(@class,'wsite-content-title')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # Iterate every h2 title individually — some wsite-section-wrap blocks
        # contain multiple listings stacked under separate h2s, so we must
        # parse per-h2 rather than per-section-wrap.
        all_h2s = tree.xpath("//h2[contains(@class,'wsite-content-title')]")

        for h2 in all_h2s:
            try:
                obj = self.parse_listing(h2)
                # Skip None (header/banner blocks) and any sold properties
                if obj and obj["saleType"] != "Sold":
                    self.results.append(obj)
            except Exception as e:
                print(f"[WARN] Skipped block due to error: {e}")
                continue

        self.driver.quit()

        return self.results

        # ===================== PARSE PROPERTY ===================== #

    def parse_listing(self, h2):
        """
        Parse a single listing from its h2 element.
        Collects content by walking siblings of the h2 up to the next h2.
        """
        from lxml import etree

        # ---------- RAW TITLE ---------- #
        raw_title = self._clean(" ".join(h2.itertext()))

        # Skip page header and "Download Property File for..." sub-headings
        if not raw_title:
            return None
        if raw_title.upper().startswith("CURRENT PROPERTIES"):
            return None
        if re.search(r'^download\s+property\s+file', raw_title, re.IGNORECASE):
            return None

        # ---------- COLLECT SIBLING CONTENT UNTIL NEXT h2 ---------- #
        # Walk forward through all following siblings in the same parent,
        # and also look one level up if the h2 is inside a nested div.
        sibling_nodes = []

        def collect_siblings(node):
            """Yield all following siblings of node, stopping at next h2."""
            for sib in node.itersiblings():
                if sib.tag == 'h2' and 'wsite-content-title' in (sib.get('class') or ''):
                    return
                sibling_nodes.append(sib)

        collect_siblings(h2)

        # If no siblings found at this level, try parent level
        if not sibling_nodes:
            parent = h2.getparent()
            if parent is not None:
                collect_siblings(parent)

        # ---------- DESCRIPTION: from paragraph divs in siblings ---------- #
        description_parts = []
        for node in sibling_nodes:
            for p in node.xpath(".//*[contains(@class,'paragraph')]") or [node] if 'paragraph' in (node.get('class') or '') else []:
                description_parts.append(" ".join(p.itertext()))
        detailed_description = self._clean(" ".join(description_parts))

        # Fallback: if no paragraph divs found, grab all text from siblings
        if not detailed_description:
            detailed_description = self._clean(" ".join(
                " ".join(n.itertext()) for n in sibling_nodes
            ))

        # ---------- FILTER: skip blocks with no UK postcode ---------- #
        combined_text = raw_title + " " + detailed_description
        if not re.search(r'[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}', combined_text, re.IGNORECASE):
            return None

        # ---------- DISPLAY ADDRESS (multi-step stripping) ---------- #
        display_address = raw_title

        # Step 1: Strip leading "PROPERTY TO LET" prefix
        display_address = re.sub(
            r'^([\w\s]*?\bTO\s+LET\b[\w\s,]*?)\s+(?=[A-Z0-9].*,)',
            '', display_address, flags=re.IGNORECASE
        ).strip()

        # Step 2: Strip "TO LET" and everything after it when mid-title
        display_address = re.sub(
            r'\s+TO\s+LET\b.*$',
            '', display_address, flags=re.IGNORECASE
        ).strip()

        # Step 3: Strip trailing status tokens (NOW LET, SOLD, UNDER OFFER, etc.)
        display_address = re.sub(
            r'[\s\-–\.]+\s*(NOW\s+)?(LET|SOLD|UNDER\s+OFFER|FREEHOLD\b.*|'
            r'LEASE\s+ASSIGNMENT\b.*|FREEHOLD\s+ACQUIRED\b.*|GROUND\s+FLOOR\s+LET)\s*$',
            '', display_address, flags=re.IGNORECASE
        ).strip().rstrip(',').strip()

        # Step 4: Strip anything after ' – ' or ' - ' (description appended after dash)
        #   e.g. '100 Upper Wickham Lane, Welling, DA16 3HQ – Land with Small Office Suite'
        display_address = re.sub(
            r'\s+[–\-]\s+.+$',
            '', display_address, flags=re.IGNORECASE
        ).strip().rstrip(',').strip()

        # ---------- IMAGES ---------- #
        images = []
        for node in sibling_nodes:
            for img in node.xpath(".//img/@src"):
                if not img.startswith("//www.weebly.com"):
                    images.append(urljoin(self.DOMAIN, img))

        # ---------- BROCHURE ---------- #
        brochure_urls = list(dict.fromkeys([
            urljoin(self.DOMAIN, href)
            for node in sibling_nodes
            for href in node.xpath(".//a[contains(@href,'.pdf')]/@href")
        ]))

        # ---------- SALE TYPE ---------- #
        sale_type = self.normalize_sale_type(raw_title, detailed_description)
        
        if sale_type== 'Sold':
            return None

        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(detailed_description, sale_type)

        # ---------- PROPERTY SUB-TYPE ---------- #
        property_sub_type = self.extract_property_sub_type(raw_title, detailed_description)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        obj = {
            "listingUrl": self.BASE_URL,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address + " " + detailed_description),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "NJWE",
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

    def normalize_sale_type(self, title: str, description: str) -> str:
        """
        Determine sale type from title first, then description.

        Priority order:
          1. Sold / freehold sold  →  "Sold"
          2. Under offer           →  "Under Offer"
          3. Explicit 'to let' /
             'lease assignment'    →  "To Let"
          4. 'now let' / bare 'let'→  "Let"   (already transacted)
          5. For sale / freehold   →  "For Sale"
        """
        combined = (title + " " + description).lower()

        if re.search(r'\bsold\b', combined):
            return "Sold"

        if re.search(r'\bunder\s+offer\b', combined):
            return "For Sale"

        if re.search(r'\bto\s+let\b', combined):
            return "To Let"

        if re.search(r'\blease\s+assignment\b', combined):
            return "To Let"

        if re.search(r'\b(now\s+)?let\b', combined):
            return "To Let"

        if re.search(r'\bfor\s+sale\b', combined):
            return "For Sale"

        if re.search(r'\bfreehold\b', combined):
            return "For Sale"

        return ""

    def extract_numeric_price(self, text: str, sale_type: str) -> str:
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
            "per annum", "pa", "per year", "pcm",
            "per month", "pw", "per week", "rent"
        ]):
            return ""

        m = re.search(
            r"(?:\u00a3|\u00c2\u00a3|\u20ac|\u00e2\u201a\u00ac)\s*"
            r"(\d+(?:,\d{3})*(?:\.\d+)?)(\s*[mk])?",
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

    def extract_size(self, text: str) -> tuple:
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

        # Square metres (fallback if no sqft found)
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

        # Hectares (fallback if no acres found)
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

    def extract_property_sub_type(self, title: str, description: str) -> str:
        combined = (title + " " + description).lower()

        if re.search(r'\bleisure\b', combined):
            return "Leisure"

        if re.search(r'\bretail\b', combined):
            return "Retail"

        if re.search(r'\boffice\b', combined):
            return "Office"

        if re.search(r'\bnursery\b', combined):
            return "Nursery / D1"

        if re.search(r'\bindustrial\b|\bwarehouse\b', combined):
            return "Industrial"

        if re.search(r'\bcar\s+sales\b|\bcar\s+park\b|\bcar\s+display\b', combined):
            return "Car Sales / Forecourt"

        if re.search(r'\bland\b', combined):
            return "Land"

        if re.search(r'\brestaurant\b|\bcafe\b|\bcatering\b', combined):
            return "Restaurant / Cafe"

        if re.search(r'\bclass\s+e\b', combined):
            return "Class E"

        return ""

    def extract_tenure(self, text: str) -> str:
        if not text:
            return ""

        t = text.lower()

        if "freehold" in t:
            return "Freehold"

        if "leasehold" in t:
            return "Leasehold"

        return ""

    def extract_postcode(self, text: str) -> str:
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

    def _clean(self, text: str) -> str:
        return re.sub(r"\s+", " ", text).strip()


if __name__ == "__main__":

    scraper = NJWEScraper()
    data = scraper.run()