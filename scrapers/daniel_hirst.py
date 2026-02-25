import re
from urllib.request import Request, urlopen
from urllib.parse import urljoin, urlparse, parse_qs

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class DanielHirstScraper:
    DOMAIN = "https://www.ws-residential.co.uk"
    SEARCH_URLS = [
        "https://www.ws-residential.co.uk/properties-for-sale",
        "https://www.ws-residential.co.uk/properties-to-let",
    ]
    AGENT_COMPANY = "Daniel & Hirst"

    def __init__(self):
        self.results = []
        self.seen_urls = set()
        self.http_headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.page_load_strategy = "eager"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_experimental_option(
            "prefs",
            {
                "profile.managed_default_content_settings.images": 2,
            },
        )

        service = Service("/usr/bin/chromedriver")
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 20)

    # ===================== RUN ===================== #

    def run(self):
        for base_url in self.SEARCH_URLS:
            base_sale_type = "To Let" if "to-let" in base_url else "For Sale"
            current_url = base_url
            seen_pages = set()

            while True:
                if current_url in seen_pages:
                    break
                seen_pages.add(current_url)

                self.driver.get(current_url)

                try:
                    self.wait.until(EC.presence_of_element_located((
                        By.XPATH,
                        "//div[@id='searchResults']//div[contains(@class,'propertyDetails')]",
                    )))
                except Exception:
                    break

                tree = html.fromstring(self.driver.page_source)
                cards = tree.xpath("//div[@id='searchResults']//div[contains(@class,'propertyDetails')]")
                if not cards:
                    break

                for card in cards:
                    overlay_text = self._clean(" ".join(
                        card.xpath(".//span[contains(@class,'overlay')]/text()")
                    )).lower()

                    if "sold" in overlay_text or "let agreed" in overlay_text:
                        continue

                    href = self._clean(" ".join(
                        card.xpath("(.//a[contains(@href,'property-details.php')]/@href)[1]")
                    ))
                    if not href:
                        continue

                    listing_url = self._normalize_listing_url(
                        urljoin(self.DOMAIN, href),
                        base_sale_type
                    )
                    listing_key = self._listing_key(listing_url)
                    if listing_key in self.seen_urls:
                        continue
                    self.seen_urls.add(listing_key)

                    try:
                        obj = self.parse_listing(listing_url, base_sale_type)
                        if obj:
                            self.results.append(obj)
                    except Exception:
                        continue

                has_next = bool(tree.xpath(
                    "//div[contains(@class,'paging')]//a[contains(@class,'paginationButton') and contains(.,'Next')]"
                ))
                if not has_next:
                    break

                next_href = self._clean(" ".join(
                    tree.xpath(
                        "//div[contains(@class,'paging')]//a[contains(@class,'paginationButton') and contains(.,'Next')][1]/@href"
                    )
                ))
                if not next_href:
                    break

                current_url = urljoin(self.DOMAIN + "/", next_href)

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url, sale_type):
        tree = self._fetch_detail_tree(url)
        if tree is None:
            return None

        display_address = self._clean(" ".join(
            tree.xpath("//div[@id='propertyTitle']//h1/text()")
        ))

        price_text = self._clean(" ".join(
            tree.xpath("//div[@id='propertyTitle']//p[contains(@class,'price')]//text()")
        ))

        feature_items = [
            self._clean(t)
            for t in tree.xpath("//div[contains(@class,'features')]//ul/li//text()")
            if self._clean(t)
        ]
        features_text = " | ".join(feature_items)

        property_details = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'description')]//p//text()")
        ))

        detailed_description = property_details

        property_sub_type = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'features')]//ul/li"
                "[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'bedroom')][1]/text()"
            )
        ))

        property_images = []
        for src in tree.xpath("//div[@id='slider']//img/@src"):
            full_src = urljoin(self.DOMAIN, src)
            if full_src and full_src not in property_images:
                property_images.append(full_src)

        brochure_urls = []
        for href in tree.xpath(
            "//div[contains(@class,'quickLinks')]//a"
            "[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'brochure')]/@href"
            " | //a[contains(@href,'/Brochure/')]/@href"
        ):
            full_url = urljoin(self.DOMAIN, href)
            if full_url not in brochure_urls:
                brochure_urls.append(full_url)

        all_text_for_extraction = self._clean(" ".join(
            part for part in [price_text, features_text, detailed_description, display_address] if part
        ))
        size_ft, size_ac = self.extract_size(all_text_for_extraction)
        tenure = self.extract_tenure(all_text_for_extraction)
        price = self.extract_numeric_price(all_text_for_extraction, sale_type)

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
            "agentCompanyName": self.AGENT_COMPANY,
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }

        print("*****"*10)
        print(obj)
        print("*****"*10)
        return obj 

    # ===================== HELPERS ===================== #

    def _normalize_listing_url(self, url, sale_type):
        parsed = urlparse(url)
        prop_id = parse_qs(parsed.query).get("id", [""])[0]
        if not prop_id:
            return url
        s_param = "lettings" if sale_type == "To Let" else "sales"
        return f"{self.DOMAIN}/property-details.php?s={s_param}&id={prop_id}"

    def _listing_key(self, url):
        parsed = urlparse(url)
        prop_id = parse_qs(parsed.query).get("id", [""])[0]
        return prop_id or url

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = text.replace("ft²", "sq ft")
        text = text.replace("m²", "sqm")
        text = re.sub(r"[–—−]", "-", text)

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
                r"(sqm|sq\.?\s*m|m2|square\s*metres|square\s*meters)",
                text,
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm_value = min(a, b) if b else a
                size_ft = round(sqm_value * 10.7639, 3)

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(acres?|acre|ac\.?)",
            text,
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        if not size_ac:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
                r"(hectares?|ha)",
                text,
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

        if any(k in t for k in ["poa", "price on application", "upon application", "on application"]):
            return ""
        if any(k in t for k in ["per annum", "per year", "pcm", "per month", "pw", "per week"]):
            return ""
        if re.search(r"\bpa\b", t):
            return ""
        if re.search(r"\brent(?:al)?\b", t):
            return ""

        m = re.search(r"[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?", t)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))
        if "m" in m.group(0):
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
        full_pattern = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b"
        partial_pattern = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\b"

        match = re.search(full_pattern, text)
        if match:
            return match.group().strip()

        match = re.search(partial_pattern, text)
        return match.group().strip() if match else ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""

    def _fetch_detail_tree(self, url):
        try:
            req = Request(url, headers=self.http_headers)
            with urlopen(req, timeout=12) as response:
                content = response.read()
            tree = html.fromstring(content)
            has_title = bool(tree.xpath("//div[@id='propertyTitle']//h1"))
            if has_title:
                return tree
        except Exception:
            pass

        try:
            self.driver.get(url)
            self.wait.until(EC.presence_of_element_located((
                By.XPATH,
                "//div[@id='propertyTitle']//h1",
            )))
            return html.fromstring(self.driver.page_source)
        except Exception:
            return None
