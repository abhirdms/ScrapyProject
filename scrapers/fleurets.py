import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class FleuretsScraper:
    BASE_URL = "https://www.fleurets.com/search.html"
    DOMAIN = "https://www.fleurets.com"

    def __init__(self):
        self.results = []
        self.seen_urls = set()

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        self.driver = webdriver.Chrome(
            service=Service("/usr/bin/chromedriver"),
            options=chrome_options,
        )
        self.wait = WebDriverWait(self.driver, 20)
        self.detail_driver = webdriver.Chrome(
            service=Service("/usr/bin/chromedriver"),
            options=chrome_options,
        )
        self.detail_wait = WebDriverWait(self.detail_driver, 20)

    # ===================== RUN ===================== #

    def run(self):
        self.driver.get(self.BASE_URL)

        try:
            self.wait.until(EC.presence_of_element_located((
                By.XPATH,
                "//div[@id='page-list']//div[contains(@class,'property-item')]",
            )))
        except Exception:
            self.driver.quit()
            self.detail_driver.quit()
            return self.results

        current_page = 1

        while True:
            tree = html.fromstring(self.driver.page_source)
            cards = tree.xpath("//div[@id='page-list']//div[contains(@class,'property-item')]")
            if not cards:
                break

            for card in cards:
                href = self._clean("".join(
                    card.xpath(".//a[contains(@class,'viewdetails')]/@href")
                )) or self._clean("".join(card.xpath(".//a[contains(@class,'o-item-box')]/@href")))

                if not href or href.lower().startswith("javascript:"):
                    continue

                listing_url = urljoin(self.DOMAIN, href)
                if listing_url in self.seen_urls:
                    continue
                self.seen_urls.add(listing_url)

                listing_summary = {
                    "title": self._clean(" ".join(card.xpath(".//h3[contains(@class,'font-weight-bold')]//text()"))),
                    "address": self._clean(" ".join(card.xpath(".//address//text()"))),
                    "price_text": self._clean(" ".join(card.xpath(".//span[contains(@class,'price')]//text()"))),
                    "tenure_text": self._clean(" ".join(card.xpath(".//span[contains(@class,'tenure')]//text()"))),
                    "summary_text": self._clean(" ".join(card.xpath(".//div[contains(@class,'o-content')]//li//text()"))),
                    "features_text": self._clean(" ".join(card.xpath(".//ul[contains(@class,'features-list')]//li//text()"))),
                    "image": self._clean("".join(card.xpath(".//img[contains(@class,'img-fluid')][1]/@src"))),
                    "email_href": self._clean("".join(card.xpath(".//a[starts-with(@href,'mailto:')][1]/@href"))),
                }

                try:
                    obj = self.parse_listing(listing_url, listing_summary)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

            next_page = current_page + 1
            next_xpath = (
                f"//a[contains(@class,'pageclick') and normalize-space(@data-page)='{next_page}']"
            )

            if not self.driver.find_elements(By.XPATH, next_xpath):
                break

            current_first_href = self._clean("".join(
                tree.xpath(
                    "(//div[@id='page-list']//div[contains(@class,'property-item')]"
                    "//a[contains(@class,'viewdetails')]/@href)[1]"
                )
            ))

            next_btn = self.driver.find_element(By.XPATH, next_xpath)
            self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", next_btn)
            self.driver.execute_script("arguments[0].click();", next_btn)

            try:
                self.wait.until(lambda d: bool(
                    d.find_elements(
                        By.XPATH,
                        f"//li[contains(@class,'page-item') and contains(@class,'active')]"
                        f"/a[contains(@class,'pageclick') and normalize-space(@data-page)='{next_page}']",
                    )
                ))
                self.wait.until(lambda d: (
                    self._clean(
                        d.find_element(
                            By.XPATH,
                            "(//div[@id='page-list']//div[contains(@class,'property-item')]"
                            "//a[contains(@class,'viewdetails')])[1]",
                        ).get_attribute("href")
                    ) != urljoin(self.DOMAIN, current_first_href)
                ))
            except Exception:
                break

            current_page = next_page

        self.driver.quit()
        self.detail_driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url, listing_summary):
        self.detail_driver.get(url)

        self.detail_wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h1[contains(@class,'o-title')]",
        )))

        tree = html.fromstring(self.detail_driver.page_source)

        title = self._clean(" ".join(tree.xpath("//h1[contains(@class,'o-title')]//text()")))
        address = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'property-meta')]//address//text()")
        ))
        display_address = self._clean(" ".join(part for part in [title, address] if part))

        detail_bullets = self._clean(" ".join(
            tree.xpath("//div[@id='property-details']//li//text()")
        ))
        contact_text = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'alert-info')]//text()")
        ))
        detailed_description = self._clean(" ".join(
            part
            for part in [
                detail_bullets,
                listing_summary.get("summary_text", ""),
                listing_summary.get("features_text", ""),
                contact_text,
            ]
            if part
        ))

        detail_price_text = self.get_meta_value(tree, "PRICE")
        detail_tenure_text = self.get_meta_value(tree, "TENURE")

        price_text = detail_price_text or listing_summary.get("price_text", "")
        tenure_text = detail_tenure_text or listing_summary.get("tenure_text", "")

        property_sub_type = self.extract_property_sub_type(url)
        sale_type = self.normalize_sale_type(" ".join([url, price_text, detailed_description, tenure_text]))
        size_ft, size_ac = self.extract_size(detailed_description)
        tenure = self.extract_tenure(" ".join([tenure_text, detailed_description]))
        # Prefer explicit price fields first; avoid sale/rent keyword noise in description.
        price_input_text = price_text or detail_price_text or listing_summary.get("price_text", "")
        if not price_input_text:
            price_input_text = detailed_description
        price = self.extract_numeric_price(price_input_text, sale_type)

        property_images = []
        for src in tree.xpath(
            "//div[contains(@class,'property-carousel')]//img/@src"
        ):
            full = urljoin(self.DOMAIN, src)
            if full and full not in property_images:
                property_images.append(full)

        if not property_images and listing_summary.get("image"):
            property_images.append(urljoin(self.DOMAIN, listing_summary.get("image")))

        brochure_urls = []
        for href in tree.xpath("//a[contains(translate(@href,'PDF','pdf'),'.pdf')]/@href"):
            full = urljoin(self.DOMAIN, href)
            if full not in brochure_urls:
                brochure_urls.append(full)

        listing_email = listing_summary.get("email_href", "")
        agent_email = ""
        if listing_email.startswith("mailto:"):
            agent_email = listing_email.replace("mailto:", "", 1).split("?", 1)[0].strip()

        phone_match = re.search(r"\b0\d{9,10}\b", contact_text.replace(" ", ""))
        agent_phone = phone_match.group(0) if phone_match else ""

        obj = {
            "listingUrl": url,
            "displayAddress": display_address or listing_summary.get("address", ""),
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address or listing_summary.get("address", "")),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Fleurets",
            "agentName": "",
            "agentCity": "",
            "agentEmail": agent_email,
            "agentPhone": agent_phone,
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }

        print("**"*20)
        print(obj)
        print("**"*20)

        return obj

    # ===================== HELPERS ===================== #

    def get_meta_value(self, tree, label):
        return self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'property-details')]"
                f"//div[contains(@class,'item')][.//div[contains(@class,'name') and normalize-space()='{label}']]"
                "//div[contains(@class,'value')]//text()"
            )
        ))

    def extract_property_sub_type(self, url):
        if not url:
            return ""

        path = url.lower().split("/properties/", 1)
        if len(path) < 2:
            return ""

        parts = [p for p in path[1].split("/") if p]
        if len(parts) < 2:
            return ""

        raw = parts[1]
        raw = raw.replace("-for-sale", "")
        raw = raw.replace("-to-let", "")
        raw = raw.replace("-for-rent", "")
        raw = raw.replace("-", " ")
        return self._clean(raw.title())

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = text.replace("ft2", "sq ft")
        text = text.replace("ft²", "sq ft")
        text = text.replace("m2", "sqm")
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
                r"(sqm|sq\.?\s*m|square\s*metres|square\s*meters)",
                text,
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm = min(a, b) if b else a
                size_ft = round(sqm * 10.7639, 3)

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac|ha|hectares?)",
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
        if not text:
            return ""

        if sale_type and sale_type.lower() != "for sale":
            return ""

        t = text.lower()

        if any(k in t for k in ["poa", "price on application", "upon application", "on application"]):
            return ""

        rent_like_patterns = [
            r"\bper\s+annum\b",
            r"\bper\s+year\b",
            r"\bper\s+month\b",
            r"\bper\s+week\b",
            r"\bp\.?\s*a\.?\b",
            r"\bpcm\b",
            r"\bpw\b",
            r"\bto\s+let\b",
            r"\bto\s+rent\b",
            r"\brent\b",
            r"\brental\b",
        ]
        if any(re.search(pattern, t) for pattern in rent_like_patterns):
            return ""

        m = re.search(r"[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)(\s*[mk])?", t)
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

        has_sale = any(k in t for k in ["for sale", "sale", "stc", "sstc", "oiro", "oieo"])
        has_let = any(k in t for k in ["to let", "to rent", "let", "lease", "letting"])

        if has_sale and has_let:
            return "For Sale"
        if has_sale:
            return "For Sale"
        if has_let:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
