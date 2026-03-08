import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class MpRealEstateScraper:
    BASE_URL = "https://www.mprealestate.co.uk/projects.php"
    DOMAIN = "https://www.mprealestate.co.uk"

    # All h2 sections to scrape listings from
    TARGET_SECTIONS = [
        "New Developments / Available Properties",
        "Investment Properties",
    ]

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

        try:
            self.wait.until(EC.presence_of_element_located((
                By.XPATH,
                "//h2[normalize-space()='New Developments / Available Properties']",
            )))
        except Exception:
            self.driver.quit()
            return self.results

        tree = html.fromstring(self.driver.page_source)

        # Scrape all target sections
        for section_name in self.TARGET_SECTIONS:
            section_cards = self.extract_section_cards(tree, section_name)
            for card in section_cards:
                try:
                    obj = self.parse_listing(card)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, card):
        display_address = card.get("title", "")
        detailed_description = card.get("description", "")

        sale_type = self.normalize_sale_type(" ".join([
            display_address,
            detailed_description,
        ]))
        size_ft, size_ac = self.extract_size(detailed_description)
        tenure = self.extract_tenure(detailed_description)
        price = self.extract_numeric_price(detailed_description, sale_type)

        obj = {
            "listingUrl": card.get("listing_url", self.BASE_URL),
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": card.get("property_images", []),
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": card.get("brochure_urls", []),
            "agentCompanyName": "MP Real Estate",
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

    # ===================== SECTION EXTRACTOR ===================== #

    def extract_section_cards(self, tree, section_name):
        cards = []

        headings = tree.xpath(f"//h2[normalize-space()='{section_name}']")
        if not headings:
            return cards

        section_heading = headings[0]

        for h3 in section_heading.xpath(
            f"./following-sibling::h3[preceding-sibling::h2[1][normalize-space()='{section_name}']]"
        ):
            title = self._clean(" ".join(h3.xpath(".//text()")))
            if not title:
                continue

            description_parts = []
            brochure_urls = []
            external_urls = []
            property_images = []

            node = h3.getnext()
            while node is not None:
                tag = (node.tag or "").lower()
                if tag in {"h2", "h3"}:
                    break

                description_text = self._clean(" ".join(node.xpath(".//text()")))
                if description_text:
                    description_parts.append(description_text)

                for href in node.xpath(".//a/@href"):
                    full = urljoin(self.DOMAIN, href)
                    if ".pdf" in (href or "").lower():
                        if full not in brochure_urls:
                            brochure_urls.append(full)
                    else:
                        if full not in external_urls:
                            external_urls.append(full)

                for src in node.xpath(".//img/@src"):
                    full = urljoin(self.DOMAIN, src)
                    if full not in property_images:
                        property_images.append(full)

                node = node.getnext()

            # Determine best listing URL: PDF > external link > base URL
            if brochure_urls:
                listing_url = brochure_urls[0]
            elif external_urls:
                listing_url = external_urls[0]
            else:
                listing_url = self.BASE_URL

            cards.append({
                "title": title,
                "description": self._clean(" ".join(description_parts)),
                "brochure_urls": brochure_urls,
                "external_urls": external_urls,
                "property_images": property_images,
                "listing_url": listing_url,
                "section": section_name,
            })

        return cards

    # ===================== HELPERS ===================== #

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = text.replace("ft2", "sq ft")
        text = text.replace("ft\u00b2", "sq ft")
        text = text.replace("m2", "sqm")
        text = text.replace("m\u00b2", "sqm")
        text = re.sub(r"[\u2013\u2014\u2212]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*feet)",
            text,
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        if not size_ft:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
                r"(sqm|sq\.?\s*m|square\s*metres|square\s*meters)",
                text,
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm = min(a, b) if b else a
                size_ft = round(sqm * 10.7639, 3)

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(acres?|acre|ac\.?|ha|hectares?)",
            text,
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            value = min(a, b) if b else a
            unit = m.group(3)
            if unit and ("ha" in unit or "hectare" in unit):
                value = value * 2.47105
            size_ac = round(value, 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if sale_type and sale_type != "For Sale":
            return ""

        if not text:
            return ""

        t = text.lower()

        if any(k in t for k in [
            "poa", "price on application", "upon application", "on application"
        ]):
            return ""

        if any(k in t for k in [
            "per annum", "pa", "per year", "pcm", "per month", "pw", "per week", "rent"
        ]):
            return ""

        m = re.search(r"(?:\u00a3|\u00c2\u00a3|\u20ac|\u00e2\u201a\u00ac)\s*(\d+(?:,\d{3})*(?:\.\d+)?)(\s*[mk])?", t)
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

    def extract_postcode(self, text):
        if not text:
            return ""

        t = text.upper()
        full_pattern = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b"
        partial_pattern = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\b"

        match = re.search(full_pattern, t)
        if match:
            return match.group().strip()

        match = re.search(partial_pattern, t)
        return match.group().strip() if match else ""

    def normalize_sale_type(self, text):
        t = (text or "").lower()
        if any(k in t for k in ["for sale", "sale", "oieo", "oiro", "stc", "sstc"]):
            return "For Sale"
        if any(k in t for k in ["to let", "to rent", "rent", "lease"]):
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
