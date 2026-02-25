import re
import time
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

from lxml import html


class DavisonBlackettScraper:
    BASE_URL = "http://www.davisonblackett.com/db_property_listings.html"
    DOMAIN = "http://www.davisonblackett.com"

    def __init__(self):
        self.results = []
        self.seen_urls = set()

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--ignore-certificate-errors")
        chrome_options.add_argument("--allow-insecure-localhost")
        chrome_options.add_argument("--disable-web-security")
        # Spoof a real browser user-agent to avoid bot blocking
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

        service = Service("/usr/bin/chromedriver")
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.set_page_load_timeout(60)
        self.wait = WebDriverWait(self.driver, 30)

    # ===================== RUN ===================== #

    def run(self):
        try:
            self.driver.get(self.BASE_URL)
        except WebDriverException:
            self.driver.quit()
            return self.results

        # Give the page extra time to settle
        time.sleep(5)

        # Try waiting for detail cards; fall back to parsing page source directly
        try:
            self.wait.until(EC.presence_of_element_located((
                By.XPATH,
                "//div[contains(@class,'detail')]"
            )))
        except TimeoutException:
            pass

        # Parse the page source with lxml regardless of wait outcome
        page_source = self.driver.page_source
        tree = html.fromstring(page_source)

        # Extract all listing hrefs from the page source
        # Matches links inside .detail cards
        detail_links = tree.xpath(
            "//div[contains(@class,'listings')]"
            "//div[contains(@class,'detail')]"
            "//a/@href"
        )

        # Fallback: grab any .html links that look like property pages
        if not detail_links:
            detail_links = tree.xpath(
                "//div[contains(@class,'detail')]//a/@href"
            )

        if not detail_links:
            self.driver.quit()
            return self.results


        # Also extract listing context from page source using lxml
        listing_contexts = self._extract_all_listing_contexts(tree)

        for idx, href in enumerate(detail_links):
            if not href or not href.endswith(".html"):
                continue

            url = urljoin(self.DOMAIN, href)

            if url in self.seen_urls:
                continue
            self.seen_urls.add(url)

            context = listing_contexts.get(href, {})

            try:
                obj = self.parse_listing(url, context)
                if obj:
                    self.results.append(obj)
            except Exception:

                continue

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url, listing_context=None):

        try:
            self.driver.get(url)
        except WebDriverException:
            return None

        time.sleep(2)

        # Wait for locWrap; don't crash if it times out
        try:
            self.wait.until(EC.presence_of_element_located((
                By.XPATH,
                "//div[contains(@class,'locWrap')]"
            )))
        except TimeoutException:
            pass

        tree = html.fromstring(self.driver.page_source)

        # ---------- SALE TYPE ---------- #
        # <h2><span>For Sale</span><br>1.18 acres Development Land</h2>
        sale_type_raw = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'locWrap')]//h2/span/text()")
        ))
        if not sale_type_raw:
            sale_type_raw = (listing_context or {}).get("status", "")

        sale_type = self.normalize_sale_type(sale_type_raw)

        # ---------- TITLE LINE (SIZE + SUBTYPE) ---------- #
        # Text sits as the tail of the <br> element inside <h2>
        title_line = ""
        h2_nodes = tree.xpath("//div[contains(@class,'locWrap')]//h2")
        if h2_nodes:
            h2 = h2_nodes[0]
            tails = [br.tail.strip() for br in h2.findall("br") if br.tail and br.tail.strip()]
            title_line = self._clean(" ".join(tails))

        if not title_line:
            title_line = (listing_context or {}).get("size", "")

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'locWrap')]//p/strong/text()")
        ))
        if not display_address:
            display_address = (listing_context or {}).get("location", "")

        # ---------- DESCRIPTION ---------- #
        # <p> without <strong> or <a> children inside txtPanel
        description_parts = tree.xpath(
            "//div[contains(@class,'locWrap')]"
            "//div[contains(@class,'txtPanel')]"
            "//p[not(.//strong) and not(.//a)]//text()"
        )
        detailed_description = self._clean(" ".join(description_parts))

        if not detailed_description:
            description_parts = tree.xpath(
                "//div[contains(@class,'locWrap')]"
                "//p[not(.//strong) and not(.//a)]//text()"
            )
            detailed_description = self._clean(" ".join(description_parts))

        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type = (
            self.extract_sub_type(title_line)
            or (listing_context or {}).get("property_sub_type", "")
        )

        # ---------- SIZE ---------- #
        size_source = " ".join(filter(None, [
            title_line,
            detailed_description,
            (listing_context or {}).get("size", ""),
        ]))
        size_ft, size_ac = self.extract_size(size_source)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(
            " ".join(filter(None, [title_line, detailed_description])),
            sale_type
        )

        # ---------- IMAGES ---------- #
        property_images = [
            urljoin(self.DOMAIN, src)
            for src in tree.xpath("//div[contains(@class,'imgPanel')]//img/@src")
            if src
        ]
        if not property_images and (listing_context or {}).get("image"):
            property_images = [urljoin(self.DOMAIN, listing_context["image"])]
        property_images = list(dict.fromkeys(property_images))

        # ---------- BROCHURE ---------- #
        brochure_urls = list(dict.fromkeys([
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@class,'pdf')]/@href")
        ]))

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Davison Blackett",
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

    # ===================== CONTEXT EXTRACTION ===================== #

    def _extract_all_listing_contexts(self, tree):
        """
        Parse listing cards from the lxml tree of the listings page.
        Returns a dict keyed by href → context dict.
        """
        contexts = {}
        cards = tree.xpath(
            "//div[contains(@class,'listings')]//div[contains(@class,'detail')]"
        )
        for card in cards:
            href_list = card.xpath(".//a/@href")
            if not href_list:
                continue
            href = href_list[0]

            # Status from h2 text
            h2_texts = card.xpath(".//h2//text()")
            status = self._clean(" ".join(h2_texts))

            # Type / Size / Location from <p><span>Label:</span> Value</p>
            def pick_label(label):
                # Match <p><span>Label:</span> Value text</p>
                nodes = card.xpath(
                    f".//p[span[normalize-space(text())='{label}:']]"
                )
                if nodes:
                    # Get all text inside the <p>, skip the span text
                    full_text = "".join(nodes[0].itertext())
                    # Remove the label prefix
                    value = re.sub(
                        rf"^\s*{re.escape(label)}\s*:\s*", "", full_text, flags=re.I
                    )
                    return self._clean(value)
                return ""

            property_sub_type = pick_label("Type")
            size = pick_label("Size")
            location = pick_label("Location")

            # Image src
            img_srcs = card.xpath(".//img/@src")
            image = img_srcs[0] if img_srcs else ""

            contexts[href] = {
                "status": status,
                "property_sub_type": property_sub_type,
                "size": size,
                "location": location,
                "image": image,
            }

        return contexts

    # ===================== FIELD EXTRACTORS ===================== #

    def extract_sub_type(self, text):
        if not text:
            return ""
        cleaned = re.sub(
            r'[\d,.]+\s*(acres?|acre|sq\.?\s*ft|sqft|sqm|sq\.?\s*m)',
            '',
            text,
            flags=re.I
        )
        return self._clean(cleaned)

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = text.replace("ft²", "sq ft").replace("m²", "sqm")
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
            a, b = float(m.group(1)), (float(m.group(2)) if m.group(2) else None)
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        # Square metres → sq ft
        if not size_ft:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(sqm|sq\.?\s*m|m2|square\s*metres|square\s*meters)',
                text
            )
            if m:
                a, b = float(m.group(1)), (float(m.group(2)) if m.group(2) else None)
                size_ft = round((min(a, b) if b else a) * 10.7639, 3)

        # Acres
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac\.?)',
            text
        )
        if m:
            a, b = float(m.group(1)), (float(m.group(2)) if m.group(2) else None)
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        # Hectares → acres
        if not size_ac:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(hectares?|ha)',
                text
            )
            if m:
                a, b = float(m.group(1)), (float(m.group(2)) if m.group(2) else None)
                size_ac = round((min(a, b) if b else a) * 2.47105, 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale" or not text:
            return ""
        t = text.lower()
        if any(k in t for k in ["poa", "price on application", "upon application", "on application"]):
            return ""
        if any(k in t for k in ["per annum", " pa ", "per year", "pcm", "per month", " pw ", "per week", "rent"]):
            return ""
        m = re.search(r'[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*(m\b)?', t)
        if not m:
            return ""
        num = float(m.group(1).replace(",", ""))
        if m.group(2):
            num *= 1_000_000
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
        text = text.upper()
        m = re.search(r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b', text)
        if m:
            return m.group().strip()
        m = re.search(r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b', text)
        return m.group().strip() if m else ""

    def normalize_sale_type(self, text):
        t = text.lower()
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t or "let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""


if __name__ == "__main__":
    scraper = DavisonBlackettScraper()
    results = scraper.run()
