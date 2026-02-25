import re
from urllib.parse import urljoin, urlparse, parse_qs

from lxml import html
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class CursonSowerbyPartnersScraper:
    DOMAIN = "https://www.cspretail.com"
    SEARCH_CONFIGS = [
        {
            "url": "https://www.cspretail.com/retail-property-search/",
            "subtype": "Retail",
        },
        {
            "url": "https://www.cspretail.com/leisure-property-search/",
            "subtype": "Leisure",
        },
    ]

    def __init__(self):
        self.results = []
        self.seen_urls = set()

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
        try:
            for config in self.SEARCH_CONFIGS:
                self._crawl_search(config["url"], config["subtype"])
            return self.results
        finally:
            self.driver.quit()

    def _crawl_search(self, base_url, property_sub_type):
        max_page = self._get_max_page(base_url)

        for page in range(1, max_page + 1):
            page_url = base_url if page == 1 else f"{base_url}?page-num={page}"
            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'cr-search-properties')]"
                )))
            except Exception:
                continue

            tree = html.fromstring(self.driver.page_source)
            listing_urls = tree.xpath(
                "//div[contains(@class,'cr-search-properties')]"
                "//div[contains(@class,'cr-link-row')]/@data-href"
            )

            if not listing_urls:
                continue

            for href in listing_urls:
                listing_url = urljoin(self.DOMAIN, href)

                if listing_url in self.seen_urls:
                    continue
                self.seen_urls.add(listing_url)

                try:
                    row = self.parse_listing(listing_url, property_sub_type)
                    if row:
                        self.results.append(row)
                except Exception:
                    continue

    def _get_max_page(self, base_url):
        self.driver.get(base_url)
        tree = html.fromstring(self.driver.page_source)

        links = tree.xpath(
            "//div[contains(@class,'cr-pagination')]//a/@href"
        )

        max_page = 1
        for href in links:
            full = urljoin(self.DOMAIN, href)
            query = parse_qs(urlparse(full).query)
            page_num = query.get("page-num", [])
            if page_num and page_num[0].isdigit():
                max_page = max(max_page, int(page_num[0]))
        return max_page

    # ===================== LISTING ===================== #

    def parse_listing(self, url, property_sub_type):
        self.driver.get(url)
        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'cr-prop-heading')]//h2"
        )))

        tree = html.fromstring(self.driver.page_source)

        display_address = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'cr-prop-heading')]//h2//text()")
        ))

        detailed_description = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'cr-property-details')]//text()")
        ))

        sale_type = self.normalize_sale_type(
            f"{display_address} {detailed_description}"
        )
        tenure = self.extract_tenure(detailed_description)
        size_ft, size_ac = self.extract_size(detailed_description)
        price = self.extract_numeric_price(detailed_description, sale_type)

        property_images = list(dict.fromkeys([
            src for src in tree.xpath(
                "//div[@id='property-carousel']//img/@src"
            ) if src
        ]))

        brochure_urls = list(dict.fromkeys([
            urljoin(self.DOMAIN, href)
            for href in tree.xpath(
                "//a[contains(@class,'cr-result-download-link')]/@href"
                " | //a[contains(@href,'.pdf') or contains(@href,'.doc') or contains(@href,'.docx')]/@href"
            )
        ]))

        agent_name = self._clean(" ".join(
            tree.xpath(
                "(//div[contains(@class,'cr-result-contacts')]//li//span/text())[1]"
            )
        ))

        agent_email = ""
        email_links = tree.xpath(
            "//div[contains(@class,'cr-result-contacts')]//a[starts-with(@href,'mailto:')]/@href"
        )
        if email_links:
            agent_email = email_links[0].replace("mailto:", "").strip()

        agent_phones = [
            self._clean(" ".join(a.xpath(".//text()")))
            for a in tree.xpath(
                "//div[contains(@class,'cr-result-contacts')]//a[starts-with(@href,'tel:')]"
            )
        ]
        agent_phone = agent_phones[0] if agent_phones else ""

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(f"{display_address} {detailed_description}"),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Curson Sowerby Partners",
            "agentName": agent_name,
            "agentCity": "",
            "agentEmail": agent_email,
            "agentPhone": agent_phone,
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }
        return obj

    # ===================== HELPERS ===================== #

    def extract_size(self, text):
        if not text:
            return "", ""

        normalized = text.lower()
        normalized = normalized.replace(",", "")
        normalized = normalized.replace("ft²", "sq ft")
        normalized = normalized.replace("m²", "sqm")
        normalized = re.sub(r"[–—−]", "-", normalized)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*feet)",
            normalized,
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        if not size_ft:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
                r"(sqm|sq\.?\s*m|m2|square\s*metres|square\s*meters)",
                normalized,
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm_value = min(a, b) if b else a
                size_ft = round(sqm_value * 10.7639, 3)

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(acres?|acre|ac\.?)",
            normalized,
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        if not size_ac:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
                r"(hectares?|ha)",
                normalized,
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                hectare_value = min(a, b) if b else a
                size_ac = round(hectare_value * 2.47105, 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale" or not text:
            return ""

        t = text.lower()
        if any(k in t for k in [
            "poa",
            "price on application",
            "upon application",
            "on application",
        ]):
            return ""

        if any(k in t for k in [
            "per annum",
            "per year",
            "pcm",
            "per month",
            "pw",
            "per week",
            "rent",
            "lease",
        ]):
            return ""

        m = re.search(r"£\s*(\d+(?:,\d{3})*(?:\.\d+)?)", t)
        if not m:
            return ""

        return str(int(float(m.group(1).replace(",", ""))))

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

    def normalize_sale_type(self, text):
        if not text:
            return ""
        t = text.lower()

        if (
            "to let" in t
            or "lease terms" in t
            or "lease " in t
            or "rent " in t
            or "per annum" in t
            or "per month" in t
        ):
            return "To Let"
        if "for sale" in t or "price guide" in t or "freehold" in t:
            return "For Sale"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
