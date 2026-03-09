import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class PJSScraper:
    BASE_URL = "https://pjsbuilds.co.uk/projects/"
    DOMAIN = "https://pjsbuilds.co.uk"

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
        self.driver.get(self.BASE_URL)

        try:
            self.wait.until(EC.presence_of_element_located((
                By.XPATH,
                "//li[contains(@class,'eg-my-handmade-blog-wrapper')]"
            )))
        except Exception:
            self.driver.quit()
            return self.results

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            "//li[contains(@class,'eg-my-handmade-blog-wrapper')]"
            "//a[contains(@class,'eg-invisiblebutton')]/@href"
        )

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

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'et_builder_inner_content')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- PROJECT TITLE ---------- #
        project_title = self._clean(" ".join(
            tree.xpath("//h1[contains(@class,'et_pb_slide_title')]/text()")
        ))

        # ---------- DISPLAY ADDRESS ---------- #
        # Primary: hero slider location
        display_address = self._clean(" ".join(
            tree.xpath(
                "//h1[contains(@class,'et_pb_slide_title')]"
                "/following::div[contains(@class,'et_pb_slide_content')][1]"
                "//p/text()"
            )
        ))

        # Backup: PROJECT LOCATION label
        if not display_address:
            display_address = self._clean(" ".join(
                tree.xpath(
                    "//p[contains(translate(text(),"
                    "'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),"
                    "'PROJECT LOCATION')]"
                    "/text()"
                )
            ))
            display_address = re.sub(r"PROJECT LOCATION:\s*", "", display_address, flags=re.I)

        # Fallback: intro heading
        if not display_address:
            display_address = self._clean(" ".join(
                tree.xpath("//div[@id='intro']//h2/text()")
            ))

        # ---------- DETAILED DESCRIPTION ---------- #
        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//div[@id='intro']//p//text()"
                "| //div[contains(@class,'et_pb_text_inner')]//p//text()"
            )
        ))

        # ---------- PROPERTY SUB TYPE ---------- #
        property_sub_type = self.extract_project_type(project_title, detailed_description)

        # ---------- PRICE ---------- #
        price = ""

        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- SALE TYPE ---------- #
        sale_type = ""

        # ---------- IMAGES ---------- #
        raw_images = tree.xpath(
            "//img/@src"
        )

        seen_imgs = set()
        property_images = []

        for src in raw_images:
            if not src:
                continue
            if "transparent.png" in src or "logo" in src.lower():
                continue
            if re.search(r'-\d+x\d+\.(jpg|jpeg|png|webp)$', src, re.I):
                continue
            if src not in seen_imgs:
                seen_imgs.add(src)
                property_images.append(src)

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
        ]

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address + " " + detailed_description),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "PJS",
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

    # ===================== HELPERS ===================== #

    def extract_project_type(self, title, description):
        combined = (title + " " + description).lower()
        if any(k in combined for k in ["listed building", "listed property", "listed farm"]):
            return "Listed Building"
        if any(k in combined for k in ["passivhaus", "passive house", "retrofit"]):
            return "PassivHaus Retrofit"
        if "orangery" in combined:
            return "Orangery Extension"
        if any(k in combined for k in ["loft conversion", "mansard"]):
            return "Loft Conversion"
        if "extension" in combined:
            return "Extension"
        if any(k in combined for k in ["refurbishment", "renovation", "remodel", "refurb"]):
            return "Refurbishment"
        if any(k in combined for k in ["new build", "newbuild"]):
            return "New Build"
        return ""

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = text.replace("ft²", "sq ft").replace("m²", "sqm")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf|square\s*feet|sq\s*feet)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        if not size_ft:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(sqm|sq\.?\s*m|m2)',
                text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm = min(a, b) if b else a
                size_ft = round(sqm * 10.7639, 3)

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac\.?)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        if not size_ac:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(hectares?|ha)',
                text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                ha = min(a, b) if b else a
                size_ac = round(ha * 2.47105, 3)

        return size_ft, size_ac

    def extract_tenure(self, text):
        t = text.lower()
        if "freehold" in t:
            return "Freehold"
        if "leasehold" in t:
            return "Leasehold"
        return ""

    def extract_postcode(self, text: str):
        if not text:
            return ""

        text = text.upper()

        full_pattern = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        partial_pattern = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        match = re.search(full_pattern, text)
        if match:
            return match.group().strip()

        match = re.search(partial_pattern, text)
        return match.group().strip() if match else ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""