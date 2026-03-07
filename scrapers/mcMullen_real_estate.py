import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class McmullenRealEstateScraper:
    BASE_URL = "https://www.mcmullenre.com/search/"
    DOMAIN = "https://www.mcmullenre.com"

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
        page = 1

        while True:
            page_url = self.BASE_URL if page == 1 else f"{self.BASE_URL}?pg={page}"
            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'search-results__results')]//tr[@data-url]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            listing_urls = self.extract_listing_urls(tree)
            if not listing_urls:
                break

            for listing_url in listing_urls:
                if listing_url in self.seen_urls:
                    continue

                self.seen_urls.add(listing_url)

                try:
                    obj = self.parse_listing(listing_url)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

            max_page = self.get_max_page(tree)
            if max_page and page >= max_page:
                break

            page += 1

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//main[contains(@class,'property')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        display_address = self._clean(" ".join(
            tree.xpath("//main[contains(@class,'property')]//h1//text()")
        ))
        if not display_address:
            return None

        section_data = self.extract_info_sections(tree)

        description = section_data.get("Description", "")
        location = section_data.get("Location", "")
        availability = section_data.get("Availability", "")
        rent = section_data.get("Rent", "")
        lease_term = section_data.get("Lease Term", "")
        lease_type = section_data.get("Lease Type", "")
        service_charge = section_data.get("Service Charge", "")
        size_text = section_data.get("Size", "")
        rates_text = section_data.get("Rates", "")
        accommodation_text = section_data.get("Accommodation", "")

        detailed_description = self._clean(" ".join(
            part for part in [
                description,
                location,
                availability,
                rent,
                lease_term,
                lease_type,
                service_charge,
                size_text,
                rates_text,
                accommodation_text,
            ] if part
        ))

        sale_type = self.normalize_sale_type(availability or detailed_description)
        tenure = self.extract_tenure(" ".join([lease_type, lease_term, detailed_description]))
        size_ft, size_ac = self.extract_size(" ".join([size_text, accommodation_text, detailed_description]))
        price = self.extract_numeric_price(" ".join([rent, detailed_description]), sale_type)

        property_images = [
            self._clean(urljoin(self.DOMAIN, src))
            for src in tree.xpath("//section[contains(@class,'property__images')]//img/@src")
            if self._clean(src)
        ]
        property_images = list(dict.fromkeys(property_images))

        brochure_urls = [
            self._clean(urljoin(self.DOMAIN, href))
            for href in tree.xpath(
                "//div[contains(@class,'property__info') or contains(@class,'property__downloads')]"
                "//a[contains(@href,'.pdf')]/@href"
                " | "
                "//main[contains(@class,'property')]"
                "//a[contains(@href,'.pdf') and not(contains(@href,'Privacy') or contains(@href,'privacy') or contains(@href,'Terms') or contains(@href,'terms') or contains(@href,'Website'))]/@href"
            )
            if self._clean(href)
        ]
        brochure_urls = list(dict.fromkeys(brochure_urls))

        agent_names = tree.xpath(
            "//div[contains(@class,'property__contacts')]//h3/text()"
        )
        agent_name = self._clean(agent_names[0]) if agent_names else ""

        agent_emails = tree.xpath(
            "//div[contains(@class,'property__contacts')]//a[starts-with(@href,'mailto:')]/@href"
        )
        agent_email = self._clean(agent_emails[0].replace("mailto:", "")) if agent_emails else ""

        contacts_blocks = tree.xpath(
            "//div[contains(@class,'property__contacts')]//p//text()"
        )
        contacts_text = self._clean(" ".join(contacts_blocks[:3]))  # limit to first contact block
        agent_phone = self.extract_phone(contacts_text)

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "McMullen Real Estate",
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

    def extract_listing_urls(self, tree):
        hrefs = tree.xpath(
            "//div[contains(@class,'search-results__results')]"
            "//tr[@data-url]/@data-url" 
            " | "
            "//div[contains(@class,'search-results__results')]"
            "//tr[@data-url]//a[contains(@class,'arrow-button')]/@href"
        )

        urls = []
        for href in hrefs:
            clean_href = self._clean(href)
            if not clean_href or "/property/" not in clean_href:
                continue
            urls.append(urljoin(self.DOMAIN, clean_href))

        return list(dict.fromkeys(urls))

    def get_max_page(self, tree):
        page_numbers = []
        for text in tree.xpath(
            "//ul[contains(@class,'search-results__pagination')]//a/text()"
        ):
            text = self._clean(text)
            if text.isdigit():
                page_numbers.append(int(text))
        return max(page_numbers) if page_numbers else 0

    def extract_info_sections(self, tree):
        data = {}

        cols = tree.xpath(
            "//main[contains(@class,'property')]"
            "//div[contains(@class,'property__info')]"
            "//div[contains(@class,'col-lg-6')][.//h2]"
        )

        for col in cols:
            heading = self._clean(" ".join(col.xpath(".//h2[1]//text()")))
            value = self._clean(" ".join(col.xpath(".//p//text() | .//table//text()")))

            if heading and value and heading not in data:
                data[heading] = value

        return data

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = text.replace("m²", "sqm")
        text = text.replace("ft²", "sq ft")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*ft)",
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
                sqm = min(a, b) if b else a
                size_ft = round(sqm * 10.7639, 3)

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
                hectares = min(a, b) if b else a
                size_ac = round(hectares * 2.47105, 3)

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
            "per annum", "pa", "per year", "pcm", "per month", "pw", "per week", "rent"
        ]):
            return ""

        matches = re.findall(r"[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*([mk])?", t)
        if not matches:
            return ""

        values = []
        for raw_num, suffix in matches:
            num = float(raw_num.replace(",", ""))
            if suffix == "m":
                num *= 1_000_000
            elif suffix == "k":
                num *= 1_000
            values.append(int(num))

        return str(min(values)) if values else ""

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
        t = text.lower()
        if "for sale" in t or "sale" in t:
            return "For Sale"
        if "to let" in t or "rent" in t or "let" in t:
            return "To Let"
        return ""

    def extract_phone(self, text):
        if not text:
            return ""

        phones = re.findall(r"(?:\+?\d[\d\s]{7,}\d)", text)
        phones = [self._clean(p) for p in phones if self._clean(p)]
        return ", ".join(dict.fromkeys(phones))

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
    