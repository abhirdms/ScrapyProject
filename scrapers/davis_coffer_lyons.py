import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class DavisCofferLyonsScraper:
    BASE_URL = "https://www.dcl.co.uk/our-properties/"
    DOMAIN = "https://www.dcl.co.uk"
    AGENT_COMPANY = "Davis Coffer Lyons"

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
        current_url = self.BASE_URL
        seen_pages = set()

        while current_url:
            if current_url in seen_pages:
                break
            seen_pages.add(current_url)

            self.driver.get(current_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'property_list')]//li[contains(@class,'equalheight')]",
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)
            listing_urls = tree.xpath(
                "//div[contains(@class,'property_list')]//li[contains(@class,'equalheight')]"
                "//h4/a/@href"
            )

            if not listing_urls:
                break

            for href in listing_urls:
                url = urljoin(self.DOMAIN, href)
                if url in self.seen_urls:
                    continue
                self.seen_urls.add(url)

                try:
                    obj = self.parse_listing(url)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

            next_href = self._clean(" ".join(
                tree.xpath("//div[contains(@class,'pagination-nav')]//a[contains(@class,'next')]/@href")
            ))
            current_url = urljoin(self.DOMAIN, next_href) if next_href else ""

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url):
        self.driver.get(url)
        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'property_list')]//h2",
        )))

        tree = html.fromstring(self.driver.page_source)

        display_address = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'property_list')]//h2/text()")
        ))

        description_text = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'sgl_desc')]//p//text()")
        ))

        location_text = self._clean(" ".join(
            tree.xpath("//h4[normalize-space()='Location']/following-sibling::p[1]//text()")
        ))

        tenure_text = self._clean(" ".join(
            tree.xpath("//h4[normalize-space()='Tenure']/following-sibling::p[1]//text()")
        ))

        planning_text = self._clean(" ".join(
            tree.xpath("//h4[normalize-space()='Planning']/following-sibling::p[1]//text()")
        ))

        detailed_description = " ".join(
            part for part in [
                description_text,
                f"Location: {location_text}" if location_text else "",
                f"Tenure: {tenure_text}" if tenure_text else "",
                f"Planning: {planning_text}" if planning_text else "",
            ] if part
        )

        status_text = (display_address + " " + detailed_description).lower()

        if any(x in status_text for x in ["acquired", "sold", "let agreed"]):
            return None

        sale_type = self.normalize_sale_type(" ".join([
            display_address,
            detailed_description,
        ]))

        property_sub_type = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'sgl_desc')]//p[contains(translate(.,"
                "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'public house')][1]/text()"
            )
        ))
        if property_sub_type:
            property_sub_type = "Public House"

        property_images = []
        for src in tree.xpath("//div[contains(@class,'header-image')]//img/@src"):
            full_src = urljoin(self.DOMAIN, src)
            if full_src and full_src not in property_images:
                property_images.append(full_src)

        brochure_urls = []

        for href in tree.xpath(
            "//div[contains(@class,'pdf-link')]//a/@href | //a[contains(@href,'.pdf')]/@href"
        ):
            full_url = urljoin(self.DOMAIN, href)

            # Skip FSQS certificate or theme PDFs
            if "FSQSCertificate" in full_url:
                continue

            # Optional: Only allow CRM brochure PDFs
            if "crm-hub" not in full_url:
                continue

            if full_url not in brochure_urls:
                brochure_urls.append(full_url)

        # Agent Name (first only)
        agent_name = self._clean(" ".join(
            tree.xpath(
                "(//div[contains(@class,'advert_address')]//h4[contains(.,'Contact')])[1]/text()"
            )
        ))
        agent_name = re.sub(r"(?i)^contact\s*", "", agent_name).strip()

        # First phone only
        agent_phone = self._clean(" ".join(
            tree.xpath(
                "(//div[contains(@class,'advert_address')]//a[starts-with(@href,'tel:')])[1]/text()"
            )
        ))

        # First email only
        agent_email = self._clean(" ".join(
            tree.xpath(
                "(//div[contains(@class,'advert_address')]//a[starts-with(@href,'mailto:')])[1]/text()"
            )
        ))

        size_ft, size_ac = self.extract_size(detailed_description)
        tenure = self.extract_tenure(detailed_description)
        price = self.extract_numeric_price(detailed_description, sale_type)

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
        if any(k in t for k in ["per annum", "pa", "per year", "pcm", "per month", "pw", "per week", "rent"]):
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

    def normalize_sale_type(self, text):
        t = text.lower()
        if "sale" in t or "freehold offers invited" in t:
            return "For Sale"
        if "rent" in t or "to let" in t or "lease" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
