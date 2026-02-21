import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class ReidRoseGregoryScraper:
    START_URLS = [
        "https://www.smithpricerrg.co.uk/property-search/?department=commercial&commercial_for_sale_to_rent=for_sale&page=1&radius=3&per_page=13&orderby=price-desc&view=grid&address_keyword=",
        "https://www.smithpricerrg.co.uk/property-search/?department=commercial&commercial_for_sale_to_rent=to_rent&page=1&radius=3&per_page=13&orderby=price-desc&view=grid&address_keyword=",
    ]
    DOMAIN = "https://www.smithpricerrg.co.uk"

    def __init__(self):
        self.results = []
        self.seen_urls = set()
        self.current_sale_type = ""

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        service = Service("/usr/bin/chromedriver")
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 25)

    def run(self):
        try:
            for base_url in self.START_URLS:
                page = 1
                source_sale_type = self.normalize_sale_type(base_url.replace("_", " "))
                self.current_sale_type = source_sale_type

                while True:
                    page_url = base_url.replace("page=1", f"page={page}")
                    self.driver.get(page_url)

                    try:
                        self.wait.until(EC.presence_of_element_located((
                            By.XPATH,
                            "//section[contains(@class,'property-container')]"
                        )))
                    except Exception:
                        break

                    tree = html.fromstring(self.driver.page_source)

                    listing_urls = [
                        urljoin(self.DOMAIN, href)
                        for href in tree.xpath(
                            "//article[contains(@class,'property--grid')]"
                            "//a[contains(@class,'property__link')]/@href"
                        )
                        if href
                    ]

                    if not listing_urls:
                        break

                    fresh_urls = []
                    for url in listing_urls:
                        dedupe_key = f"{url}||{source_sale_type}"
                        if dedupe_key in self.seen_urls:
                            continue
                        self.seen_urls.add(dedupe_key)
                        fresh_urls.append(url)

                    if not fresh_urls:
                        break

                    for url in fresh_urls:
                        try:
                            obj = self.parse_listing(url)
                            if obj:
                                self.results.append(obj)
                        except Exception:
                            continue

                    has_next = bool(
                        tree.xpath("//span[contains(@class,'property-pagination__next')]//a/@href")
                    )
                    if not has_next:
                        break

                    page += 1
                    if page > 200:
                        break
        finally:
            self.driver.quit()

        return self.results

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h1[contains(@class,'property__address-detail')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        display_address = self._clean(" ".join(
            tree.xpath("//h1[contains(@class,'property__address-detail')]//text()")
        ))

        instruction_items = tree.xpath("//ul[contains(@class,'instruction-list')]/li")
        property_sub_type = ""
        rent_or_price_text = ""
        size_block_text = ""

        for li in instruction_items:
            p_values = [
                self._clean(" ".join(p.xpath(".//text()")))
                for p in li.xpath("./p")
            ]
            p_values = [v for v in p_values if v]
            if len(p_values) < 2:
                continue

            key = p_values[0].replace("\xa0", " ").lower()
            value = p_values[1]

            if (not property_sub_type) and (
                "property sub type" in key
                or "property subtype" in key
                or "sub type" in key
                or key.strip() == "subtype"
            ):
                property_sub_type = value
            if (not property_sub_type) and "property type" in key:
                property_sub_type = value
            if (not rent_or_price_text) and "rent" in key:
                rent_or_price_text = value
            if (not size_block_text) and "size" in key:
                size_block_text = value

        if not rent_or_price_text:
            rent_or_price_text = self._clean(" ".join(
                tree.xpath("//h4[contains(@class,'property__price')]//text()")
            ))

        excerpt_text = self._clean(" ".join(
            tree.xpath("//p[contains(@class,'property__except')]//text()")
        ))
        description_text = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'property-tabs__description')]//text()")
        ))
        accommodation_text = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'accommodation-tabel')]//table//text()")
        ))
        terms_text = self._clean(" ".join(
            tree.xpath("//h2[normalize-space()='Terms']/following-sibling::p[1]//text()")
        ))

        detailed_description = self._clean(" ".join(
            part for part in [excerpt_text, description_text, accommodation_text, terms_text] if part
        ))

        size_ft, size_ac = self.extract_size(
            " ".join([size_block_text, accommodation_text, detailed_description])
        )
        sale_type = self.current_sale_type or self.normalize_sale_type(url.replace("-", " "))
        tenure = self.extract_tenure(" ".join([terms_text, detailed_description]))
        price = self.extract_numeric_price(rent_or_price_text, sale_type)

        property_images = []
        for src in tree.xpath(
            "//div[@id='property-sliders']//img/@src"
            " | //div[contains(@class,'property-tabs-gallery')]//img/@data-src"
            " | //div[contains(@class,'property-tabs-gallery')]//img/@src"
        ):
            full = urljoin(self.DOMAIN, src)
            if full and full not in property_images:
                property_images.append(full)

        brochure_urls = []
        for href in tree.xpath(
            "//a[contains(translate(normalize-space(.),"
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'download brochure')]/@href"
            " | //a[contains(@href,'.pdf')]/@href"
        ):
            full = urljoin(self.DOMAIN, href)
            if full and full not in brochure_urls:
                brochure_urls.append(full)

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
            "agentCompanyName": "Reid Rose Gregory",
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

    def get_section_text(self, tree, heading):
        return self._clean(" ".join(
            tree.xpath(
                f"//h2[normalize-space()='{heading}']/following-sibling::*[1]//text()"
            )
        ))

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower()
        text = text.replace(",", "")
        text = text.replace("ft²", "sq ft")
        text = text.replace("m²", "sqm")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*feet)",
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        if not size_ft:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
                r"(sqm|sq\.?\s*m|m2|square\s*metres|square\s*meters)",
                text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm_value = min(a, b) if b else a
                size_ft = round(sqm_value * 10.7639, 3)

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(acres?|acre|ac\.?)",
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        if not size_ac:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
                r"(hectares?|ha)",
                text
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

        if any(k in t for k in [
            "poa", "price on application", "upon application", "on application"
        ]):
            return ""

        if any(k in t for k in [
            "per annum", "pa", "per year", "pcm",
            "per month", "pw", "per week", "rent"
        ]):
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
        if "lease" in t or "to let" in t:
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
        t = (text or "").lower()
        if "for sale" in t or "for_sale" in t or "forsale" in t or "sale" in t:
            return "For Sale"
        if "to_rent" in t or "to rent" in t or "rent" in t or "to let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
