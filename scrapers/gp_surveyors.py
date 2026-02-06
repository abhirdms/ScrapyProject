import requests
import re
from lxml import html


class GpSurveyorsScraper:
    BASE_URL = "https://www.gpsurveyors.co.uk/properties/gp-properties-for-sale/"

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

        listing_urls = tree.xpath(
            "//div[contains(@class,'blog-shortcode')]//article//h2/a/@href"
        )

        for url in listing_urls:
            try:
                self.results.append(self.parse_listing(url))
            except Exception:
                continue

        return self.results

    # ---------------- LISTING ---------------- #

    def parse_listing(self, url):
        resp = requests.get(url, headers=self.HEADERS, timeout=30)
        tree = html.fromstring(resp.text)

        description = self.get_description(tree)
        summary_text = self.get_summary_text(tree)
        size_ft, size_ac = self.extract_size(summary_text)

        obj = {
            "listingUrl": url,

            # map iframe src
            "displayAddress":"",

            # price text
            "price": self.extract_numeric_price(" ".join(tree.xpath(
                "//div[contains(@class,'wpb_text_column')]//h4/text()"
            ))),

            "propertySubType": "",

            "propertyImage": tree.xpath(
                "//div[contains(@class,'wpb_gallery_slides')]//ul[contains(@class,'slides')]//li//a/@href"
            ),

            "detailedDescription": description,

            "sizeFt": size_ft,
            "sizeAc": size_ac,

            "postalCode": self.extract_postcode(summary_text),

            "brochureUrl": "",

            "agentCompanyName": "GP Surveyors",

            "agentName": (
                # FORMAT 2: "Contact Rebecca Reynard"
                self._clean(
                    " ".join(
                        tree.xpath("//h3[contains(@class,'team-name')]/text()")
                    ).replace("Contact", "").strip()
                )
                or
                # FORMAT 1: <h3>Contact</h3> → <strong>Name</strong>
                self._clean(
                    " ".join(
                        tree.xpath(
                            "//h3[normalize-space()='Contact']"
                            "/following-sibling::p[1]//strong[1]/text()"
                        )
                    )
                )
            ),
            "agentCity": "",

            "agentPhone": (
                # FORMAT 2
                self._clean(
                    " ".join(
                        tree.xpath(
                            "//div[contains(@class,'team-desc')]"
                            "//text()[contains(., '0114')]"
                        )
                    )
                )
                or
                # FORMAT 1
                self._clean(
                    " ".join(
                        tree.xpath(
                            "//h3[normalize-space()='Contact']"
                            "/following-sibling::p[2]"
                            "//text()[contains(., '0114')]"
                        )
                    )
                )
            ),

            "agentEmail": self._clean(" ".join(
                tree.xpath(
                    "//h3[normalize-space()='Contact']"
                    "/following-sibling::p"
                    "//a[starts-with(@href,'mailto:')]/text()"
                )
            )),
            "agentStreet": "",
            "agentPostcode": "",


            "tenure": self.get_tenure(description),

            "saleType": self.get_sale_type(summary_text),
        }

        return obj

    # ---------------- HELPERS ---------------- #

    def get_description(self, tree):
        texts = tree.xpath(
            "(//div[contains(@class,'vc_tta-panel-body')]"
            "[descendant::div[contains(@class,'wpb_text_column')]])[2]"
            "//div[contains(@class,'wpb_text_column')]//p//text()"
        )
        return " ".join(t.strip() for t in texts if t.strip())
    

    def get_summary_text(self, tree):
        texts = tree.xpath(
            "(//div[contains(@class,'vc_tta-panel-body')]"
            "[descendant::h5[normalize-space()='Key Property Features']])"
            "//p//text()"
        )
        return " ".join(t.strip() for t in texts if t.strip())




    def extract_size(self, text):
        if not text:
            return "", ""

        raw = (
            text.lower()
            .replace(",", "")
            .replace("–", "-")   # normalize en-dash
            .replace("—", "-")   # normalize em-dash
        )

        size_ft = ""
        size_ac = ""

        # 1️⃣ Acres (site area) — NO conversion
        acre_matches = re.findall(
            r'(\d+(?:\.\d+)?)\s*(acres?|acre|ac)\b',
            raw
        )
        if acre_matches:
            size_ac = float(acre_matches[0])

        # 2️⃣ sqm / m2 / m² → sum all
        sqm_matches = re.findall(
            r'(\d+(?:\.\d+)?)\s*(sqm|m2|m²|square\s*metres?)',
            raw
        )

        if sqm_matches:
            total_sqm = sum(float(val[0]) for val in sqm_matches)
            size_ft = int(total_sqm * 10.7639)

        # 3️⃣ sqft fallback (only if sqm not found)
        if not size_ft:
            m = re.search(r'(\d+(?:\.\d+)?)\s*(sq\s*ft|sqft|sf)\b', raw)
            if m:
                size_ft = int(float(m.group(1)))

        return size_ft, size_ac


    def extract_numeric_price(self, text):
        if not text:
            return ""

        # Normalize aggressively
        raw = (
            text.lower()
            .replace(",", "")
            .replace("\u00a0", " ")   # non-breaking space
        )

        # Ignore POA-type listings
        if any(x in raw for x in [
            "poa",
            "price on application",
            "upon application",
            "on application"
        ]):
            return ""

        prices = []

        # 1️⃣ Standard £ numbers (e.g. £65000000)
        for val in re.findall(r"£\s*(\d{4,})", raw):
            prices.append(int(val))

        # 2️⃣ Million formats
        # Handles:
        # £2.2 million
        # £2 million
        # 2.2 million
        # £2.2m
        # 2m
        million_matches = re.findall(
            r"(?:£\s*)?(\d+(?:\.\d+)?)\s*(million|m)\b",
            raw
        )

        for num, _ in million_matches:
            prices.append(int(float(num) * 1_000_000))

        return min(prices) if prices else ""




    def extract_postcode_from_map(self, tree):
        src = " ".join(tree.xpath(
            "//div[contains(@class,'vc_tta-panel')]//iframe/@src"
        ))
        return self.extract_postcode(src)

    def get_tenure(self, text):
        t = text.lower()
        if "freehold" in t:
            return "Freehold"
        if "leasehold" in t:
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
