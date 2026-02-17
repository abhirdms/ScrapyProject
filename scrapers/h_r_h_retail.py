import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class HRHRetailScraper:
    BASE_URLS = [
        "https://www.hrhretail.com/property/?pf-category%5B%5D=Agency",
        "https://www.hrhretail.com/property/?pf-category[]=Investment"
    ]
    DOMAIN = "https://www.hrhretail.com"

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

        for base_url in self.BASE_URLS:
            self.driver.get(base_url)

            self.wait.until(EC.presence_of_element_located((
                By.XPATH,
                "//article[contains(@class,'column')]"
            )))

            tree = html.fromstring(self.driver.page_source)

            listing_urls = tree.xpath(
                "//article[contains(@class,'column')]//a[contains(@class,'button-primary')]/@href"
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
            "//h1[contains(@class,'title')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//p[contains(@class,'location')]//text()")
        ))

        # ---------- SALE TYPE ---------- #
        sale_type = self.normalize_sale_type(url)

        # ---------- DESCRIPTION ---------- #
        description_parts = tree.xpath(
            """
            //article[contains(@class,'columns')]
            //p[not(contains(@class,'location'))]
            //text()
            |
            //article[contains(@class,'columns')]
            //ul/li//text()
            """
        )

        cleaned_desc = []

        for text in description_parts:
            text = self._clean(text)
            if text:
                cleaned_desc.append(text)

        detailed_description = " ".join(cleaned_desc)

        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(detailed_description, sale_type)

        # ---------- PROPERTY IMAGES (MULTIPLE IMAGES) ---------- #

        images = []

        # 1️⃣ Main featured image
        main_img = tree.xpath(
            "//div[contains(@class,'page-feature-image')]//img/@src"
        )
        if main_img:
            images.extend(main_img)

        # 2️⃣ Gallery full-size images (IMPORTANT – use <a href>, not thumbnail img src)
        gallery_imgs = tree.xpath(
            "//div[contains(@class,'thumbnail-links')]//a/@href"
        )
        if gallery_imgs:
            images.extend(gallery_imgs)

        # Make absolute + remove duplicates
        clean_images = []
        for img in images:
            full_img = urljoin(self.DOMAIN, img)
            if full_img not in clean_images:
                clean_images.append(full_img)

        property_image = clean_images  # keep as LIST (as per your schema style)


        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
        ]

        # ---------- AGENT DETAILS (UPDATED LOGIC) ---------- #

        agent_name = ""
        agent_phone = ""
        agent_email = ""

        contact_ps = tree.xpath(
            "//aside[contains(@class,'aside__single-property')]"
            "//h4[normalize-space()='Contact Details']/following-sibling::p"
        )

        # Remove empty paragraphs
        contact_ps = [
            p for p in contact_ps
            if self._clean("".join(p.xpath(".//text()")))
        ]

        # Structure is:
        # Name
        # Phone + Email
        # Name
        # Phone + Email
        if len(contact_ps) >= 2:
            agent_name = self._clean("".join(contact_ps[0].xpath(".//text()")))

            phone_text = contact_ps[1].xpath("text()")
            if phone_text:
                agent_phone = self._clean(phone_text[0])

            email = contact_ps[1].xpath(".//a[starts-with(@href,'mailto:')]/@href")
            if email:
                agent_email = email[0].replace("mailto:", "").strip()

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": property_image,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "HRH Retail",
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
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(r'(\d+(?:\.\d+)?)\s*(sq\s*ft|sqft|sf)', text)
        if m:
            size_ft = float(m.group(1))

        m = re.search(r'(\d+(?:\.\d+)?)\s*(sq\s*m|sqm|m2|m²)', text)
        if m:
            size_ft = round(float(m.group(1)) * 10.7639, 2)

        m = re.search(r'(\d+(?:\.\d+)?)\s*(acres?|acre|ac)', text)
        if m:
            size_ac = float(m.group(1))

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale":
            return ""

        if not text:
            return ""

        t = text.lower()

        if any(k in t for k in [
            "poa", "price on application", "upon application",
            "per annum", "pa", "pcm", "pw", "rent"
        ]):
            return ""

        m = re.search(r'[£]\s*(\d+(?:,\d{3})*(?:\.\d+)?)', t)
        if not m:
            return ""

        return m.group(1).replace(",", "")

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
        if "to let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
