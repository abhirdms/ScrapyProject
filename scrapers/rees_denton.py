import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class ReesDentonScraper:
    BASE_URL = "https://reesdenton.com/rd/property.nsf/all-properties?open&start={}&count=10"
    DOMAIN = "https://reesdenton.com"

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
        start = 1

        while True:
            page_url = self.BASE_URL.format(start)
            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//table[contains(@class,'property')]//tr[td[@class='location']]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            listing_urls = tree.xpath(
                "//table[contains(@class,'property')]"
                "//tr[td[@class='location']]"
                "//td[@class='select-view']//a/@href"
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

            start += 10

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h2"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//h2/text()")
        ))

        # ---------- PROPERTY TYPE ---------- #
        property_sub_type = self._clean(" ".join(
            tree.xpath("//td[normalize-space()='Type']/following-sibling::td//text()")
        ))

        # ---------- TENURE ---------- #
        tenure = self._clean(" ".join(
            tree.xpath("//td[normalize-space()='Tenure']/following-sibling::td//text()")
        ))

        # ---------- CONTACT ---------- #
        contact_href = self._clean(" ".join(
            tree.xpath("//table[contains(@class,'mainproperty')]//a[starts-with(@href,'mailto:')]/@href")
        ))
        agent_email = self.extract_email(contact_href)
        agent_name = self._clean(" ".join(
            tree.xpath("//table[contains(@class,'mainproperty')]//a[starts-with(@href,'mailto:')]//text()")
        ))
        agent_phone = self._clean(" ".join(
            tree.xpath("//table[contains(@class,'mainproperty')]//span[contains(@class,'label')]//text()")
        ))

        # ---------- SIZE ---------- #
        size_text = " ".join(
            tree.xpath("//table[contains(@class,'table-striped')]//td//text()")
        )
        size_ft, size_ac = self.extract_size(size_text)

        # ---------- PRICE / RENT ---------- #
        price_text = self._clean(" ".join(
            tree.xpath(
                "//table[contains(@class,'table-striped')]"
                "//tr[td[1][contains(translate(normalize-space(.),"
                "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'rent')"
                " or contains(translate(normalize-space(.),"
                "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'price')]]"
                "/td[last()]//text()"
            )
        ))

        # ---------- DESCRIPTION ---------- #
        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//table[contains(@class,'table-striped')]"
                "//tr[td/strong[normalize-space()='Notes']]//td//text()"
            )
        ))

        sale_type = self.normalize_sale_type(price_text, tenure, detailed_description)
        price = self.extract_numeric_price(price_text, sale_type)

        # ---------- IMAGES ---------- #
        property_images = [
            urljoin(self.DOMAIN, src)
            for src in tree.xpath("//table[@class='mainproperty']//img/@src")
            if src
        ]

        # ---------- BROCHURE ---------- #
        brochure_urls = []
        js_links = tree.xpath("//a[contains(@href,'downloadDetailsSheet')]/@href")

        for link in js_links:
            m = re.search(
                r"downloadDetailsSheet\('([^']+)'\s*,\s*'[^']+'\s*,\s*'([^']+\.pdf)'",
                link,
                re.IGNORECASE
            )
            if m:
                brochure_urls.append(
                    urljoin(self.DOMAIN, f"/rd/property.nsf/{m.group(1)}/$File/{m.group(2)}")
                )

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
            "agentCompanyName": "Rees Denton",
            "agentName": agent_name,
            "agentCity": "",
            "agentEmail": agent_email,
            "agentPhone": agent_phone,
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

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = text.replace("ft²", "sq ft")
        text = text.replace("m²", "sqm")
        text = re.sub(r"\bft\s*2\b", "sq ft", text)
        text = re.sub(r"\bm\s*2\b", "sqm", text)
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\.?\s*ft|sqft|sf)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale":
            return ""

        if not text:
            return ""

        t = text.lower()

        if any(k in t for k in ["poa", "application"]):
            return ""

        if any(k in t for k in ["per annum", "pa", "pcm", "rent"]):
            return ""

        m = re.search(r'£\s*(\d+(?:,\d{3})*(?:\.\d+)?)', text)
        if not m:
            return ""

        amount = int(float(m.group(1).replace(",", "")))
        return str(amount) if amount > 0 else ""

    def extract_postcode(self, text):
        if not text:
            return ""

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        t = text.upper()
        m = re.search(FULL, t) or re.search(PARTIAL, t)
        return m.group() if m else ""

    def extract_email(self, text):
        if not text:
            return ""
        m = re.search(r"mailto:([^?'\"]+@[^?'\"]+)", text, re.IGNORECASE)
        return m.group(1).strip() if m else ""

    def normalize_sale_type(self, price_text, tenure_text="", description_text=""):
        t_price = (price_text or "").lower()
        t_tenure = (tenure_text or "").lower()
        t_desc = (description_text or "").lower()
        merged = f"{t_price} {t_tenure} {t_desc}"

        if "for sale" in t_tenure or "for sale" in merged or "offers are invited" in merged:
            return "For Sale"
        if "to let" in merged:
            return "To Let"
        if any(k in t_price for k in ["rent", "pax", "per annum", " p.a", "pcm", "pw", "lease"]):
            return "To Let"
        if "£" in t_price:
            return "For Sale"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
