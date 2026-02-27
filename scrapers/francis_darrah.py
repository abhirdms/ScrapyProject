import re
from urllib.parse import urljoin

from lxml import html
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class FrancisDarrahScraper:
    BASE_URL = "https://www.francisdarrah.co.uk/available-properties/"
    DOMAIN = "https://www.francisdarrah.co.uk"

    def __init__(self):
        self.results = []
        self.seen_urls = set()
        self.visited_pages = set()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
        })

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        service = Service("/usr/bin/chromedriver")
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 20)

    def run(self):
        page = 1

        while True:
            page_url = self.BASE_URL if page == 1 else f"{self.BASE_URL}page/{page}/"
            if page_url in self.visited_pages:
                break
            self.visited_pages.add(page_url)
            self.driver.get(page_url)

            # If a non-existent page redirects away (often back to page 1), stop pagination.
            if page > 1:
                current_url = (self.driver.current_url or "").rstrip("/")
                expected_url = page_url.rstrip("/")
                if current_url != expected_url:
                    break

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'propertyindex')]//article/a",
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)
            cards = tree.xpath("//div[contains(@class,'propertyindex')]//article")
            if not cards:
                break

            new_urls_found = False

            for card in cards:
                status_text = self._clean(" ".join(
                    card.xpath(".//p[contains(@class,'status')]//text()")
                ))
                if self.is_sold(status_text):
                    continue

                href = card.xpath(".//a[1]/@href")
                if not href:
                    continue

                listing_url = urljoin(self.DOMAIN, href[0])
                if listing_url in self.seen_urls:
                    continue
                self.seen_urls.add(listing_url)
                new_urls_found = True

                try:
                    obj = self.parse_listing(listing_url, status_text)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

            if not new_urls_found and page > 1:
                break

            page += 1

        self.driver.quit()
        self.session.close()
        return self.results

    def parse_listing(self, url, list_status_text=""):
        resp = self.session.get(url, timeout=20)
        if resp.status_code != 200:
            return None
        tree = html.fromstring(resp.text)

        detail_status_text = self._clean(" ".join(
            tree.xpath("//aside//p[contains(@class,'status')]//text()")
        ))
        combined_status = self._clean(" ".join(
            part for part in [list_status_text, detail_status_text] if part
        ))
        if self.is_sold(combined_status):
            return None

        display_address = self._clean(" ".join(
            tree.xpath("//header/h1/text()")
        ))
        location_block = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'meta')][.//h3[normalize-space()='Location']]//p//text()")
        ))

        description_text = self._clean(" ".join(tree.xpath(
            "//div[contains(@class,'grid-lg-8')]//section"
            "/*[self::p or self::table]"
            "[not(.//a[contains(@class,'outline')])]"
            "[not(ancestor::div[contains(@class,'disclaimer')])]"
            "//text()"
        )))
        detailed_description = description_text

        sale_context = self._clean(" ".join(
            part for part in [combined_status, description_text] if part
        ))
        sale_type = self.normalize_sale_type(sale_context)
        size_ft, size_ac = self.extract_size(description_text)
        tenure = self.extract_tenure(description_text)
        price = self.extract_numeric_price(description_text, sale_type)

        property_images = self._unique([
            urljoin(self.DOMAIN, src)
            for src in tree.xpath(
                "//div[contains(@class,'propertyslides')]//img/@src | "
                "//div[contains(@class,'floorplans')]//img/@src"
            )
            if src
        ])

        brochure_urls = self._unique([
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(translate(@href,'PDF','pdf'),'.pdf')]/@href")
            if href
        ])

        effective_address = display_address or location_block
        agent_details = self.extract_agent_details(tree)

        obj = {
            "listingUrl": url,
            "displayAddress": effective_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(effective_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Francis Darrah",
            "agentName": agent_details.get("agentName", ""),
            "agentCity": agent_details.get("agentCity", ""),
            "agentEmail": agent_details.get("agentEmail", ""),
            "agentPhone": agent_details.get("agentPhone", ""),
            "agentStreet": agent_details.get("agentStreet", ""),
            "agentPostcode": agent_details.get("agentPostcode", ""),
            "tenure": tenure,
            "saleType": sale_type,
        }

        return obj

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = text.replace("ft2", "sq ft").replace("ft²", "sq ft")
        text = text.replace("m2", "sqm").replace("m²", "sqm")
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
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(acres?|acre|ac|ha|hectares?)",
            text,
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            value = min(a, b) if b else a
            unit = m.group(3)
            if unit and ("ha" in unit or "hectare" in unit):
                value *= 2.47105
            size_ac = round(value, 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if not text:
            return ""

        if sale_type and sale_type.lower() not in {"for sale", "for sale / to let"}:
            return ""

        t = text.lower()

        if any(k in t for k in ["poa", "price on application", "upon application", "on application"]):
            return ""

        if any(k in t for k in ["per annum", "pa", "per year", "pcm", "per month", "pw", "per week"]):
            return ""

        m = re.search(r"£\s*(\d+(?:,\d{3})*(?:\.\d+)?)(\s*m|\s*k)?", t)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))
        suffix = (m.group(2) or "").strip()
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

        has_sale = any([
            "for sale" in t,
            "sale agreed" in t,
            bool(re.search(r"\b(?:sstc|stc)\b", t)),
        ])
        has_let = any([
            "to let" in t,
            "to rent" in t,
            "let agreed" in t,
            "lease" in t,
            "letting" in t,
        ])

        if has_sale and has_let:
            return "For Sale"
        if has_sale:
            return "For Sale"
        if has_let:
            return "To Let"
        return ""

    def extract_agent_details(self, tree):
        details = {
            "agentCompanyName": "Francis Darrah",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
        }

        viewing_nodes = tree.xpath(
            "//aside//div[contains(@class,'meta')][.//h3[normalize-space()='Viewing']]"
        )
        if not viewing_nodes:
            return details

        viewing = viewing_nodes[0]

        company = self._clean(" ".join(viewing.xpath(".//p[2]//strong//text()")))
        if company:
            details["agentCompanyName"] = company

        contact_text = self._clean(" ".join(viewing.xpath(".//p[2]//text()")))
        m = re.search(r"contact:\s*(.*?)(?:\s+tel:|\s+email:|$)", contact_text, flags=re.I)
        if m:
            details["agentName"] = self._clean(m.group(1))

        phones = [self._clean(v) for v in viewing.xpath(".//a[starts-with(@href,'tel:')]/text()") if self._clean(v)]
        if phones:
            details["agentPhone"] = phones[0]

        emails = [v.replace("mailto:", "").strip() for v in viewing.xpath(".//a[starts-with(@href,'mailto:')]/@href")]
        emails = [v for v in emails if v]
        if emails:
            details["agentEmail"] = emails[0]

        address_lines = [
            self._clean(x).strip(" ,")
            for x in viewing.xpath(".//p[last()]/text()")
            if self._clean(x)
        ]
        address_lines = [
            line for line in address_lines
            if not line.lower().startswith(("tel:", "email:")) and "www." not in line.lower()
        ]

        if address_lines:
            details["agentStreet"] = address_lines[0]

        if len(address_lines) >= 2 and not any(ch.isdigit() for ch in address_lines[1]):
            details["agentCity"] = address_lines[1]

        details["agentPostcode"] = self.extract_postcode(" ".join(address_lines))

        return details

    def is_sold(self, text):
        t = (text or "").lower()
        sold_markers = ["sold", "let agreed", "sale agreed", "under offer", "sstc", "stc"]
        return any(marker in t for marker in sold_markers)

    def _clean(self, value):
        return " ".join(value.split()) if value else ""

    def _unique(self, values):
        seen = set()
        out = []
        for value in values:
            if value and value not in seen:
                seen.add(value)
                out.append(value)
        return out
