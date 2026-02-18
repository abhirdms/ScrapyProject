import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class LevyRealEstateScraper:
    BASE_URL = "https://www.levyrealestate.co.uk/properties"
    DOMAIN = "https://www.levyrealestate.co.uk"

    def __init__(self):
        self.results = []
        self.seen_urls = set()

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")

        service = Service("/usr/bin/chromedriver")
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 20)

    # ===================== RUN ===================== #

    def run(self):

        self.driver.get(self.BASE_URL)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'property-box')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            "//div[contains(@class,'property-box')]//a/@href"
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
            "//h1[contains(@class,'property-title')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS (USE H6 ADDRESS SECTION) ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//h6[contains(@class,'address')]/text()")
        ))

        title_text = self._clean(" ".join(
            tree.xpath("//h1[contains(@class,'property-title')]/text()")
        ))

        # ---------- DESCRIPTION ---------- #
        detailed_description = self._clean(" ".join(
            tree.xpath("//ul/li[contains(@class,'wow')]/text()")
        ))

        combined_text = f"{title_text} {detailed_description}"

        # ---------- SALE TYPE (HELPER) ---------- #
        size_ft, size_ac = self.extract_size(combined_text)


        # ---------- TENURE (FROM DESCRIPTION ONLY) ---------- #
        tenure = self.extract_tenure(combined_text)


        # ---------- SALE TYPE (HELPER) ---------- #
        sale_type = self.normalize_sale_type(display_address + " " + detailed_description)



        # ---------- IMAGES ---------- #
        property_images = [
            img.strip()
            for img in tree.xpath(
                "//div[contains(@class,'small-image-slide')]//a/@href"
            )
            if img.strip()
        ]

        # ---------- POSTCODE (FROM SAME DISPLAY ADDRESS) ---------- #
        postcode = self.extract_postcode(display_address)

        # ---------- BROCHURES ---------- #
        brochure_urls = []
        brochure_links = tree.xpath(
            "//a[contains(@class,'brochure-btn')]/@href"
        )

        for pdf in brochure_links:
            if pdf.startswith("//"):
                pdf = "https:" + pdf
            brochure_urls.append(pdf)

        # ---------- FIRST AGENT ONLY ---------- #
        first_agent = tree.xpath(
            "(//div[contains(@class,'team-member')])[1]"
        )

        agent_name = ""
        agent_email = ""
        agent_phone = ""

        if first_agent:
            first = first_agent[0]

            name = first.xpath(".//h6[contains(@class,'name')]/text()")
            agent_name = self._clean(name[0]) if name else ""

            email = first.xpath(".//a[starts-with(@href,'mailto:')]/@href")
            if email:
                agent_email = email[0].replace("mailto:", "").strip()

            phone = first.xpath(
                ".//p[contains(@class,'contacts')]/span[not(contains(@class,'icon-span'))]/text()"
            )
            if phone:
                agent_phone = self._clean(phone[0])

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": "",
            "propertySubType": "",
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": postcode,
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Levy Real Estate",
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

        text = text.lower()
        text = text.replace(",", "")  # remove commas
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        # ---------- SQ FT (handles sq.ft., sq ft, sqft, sf) ---------- #
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf)',
            text
        )

        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        # ---------- ACRES ---------- #
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac)',
            text
        )

        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        return size_ft, size_ac


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

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        t = text.upper()
        m = re.search(FULL, t) or re.search(PARTIAL, t)
        return m.group() if m else ""

    def normalize_sale_type(self, text):
        t = text.lower()
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
