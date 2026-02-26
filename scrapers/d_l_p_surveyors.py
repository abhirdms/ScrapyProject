import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class DLPSurveyorsScraper:
    BASE_URL = "https://www.dlpsurveyors.co.uk/products"
    DOMAIN = "https://www.dlpsurveyors.co.uk"
    AGENT_COMPANY = "DLP Surveyors"

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
            page_url = f"{self.BASE_URL}?Page={page}"

            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'product--listView')]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            listing_blocks = tree.xpath("//div[contains(@class,'product--listView')]")

            if not listing_blocks:
                break

            for block in listing_blocks:

                href = block.xpath(".//a[contains(@class,'product-img')]/@href")
                if not href:
                    continue

                url = urljoin(self.DOMAIN, href[0])

                if url in self.seen_urls:
                    continue
                self.seen_urls.add(url)

                # ---------- SALE TYPE FROM LISTING ---------- #
                listing_text = " ".join(
                    block.xpath(".//h3[contains(@class,'product_location')]//a/text()")
                ).strip()

                sale_type = self.normalize_sale_type_from_listing(listing_text)

                # ---------- SIZE FROM LISTING ---------- #
                size_ft_listing, size_ac_listing = self.extract_size(listing_text)

                try:
                    obj = self.parse_listing(
                        url,
                        sale_type,
                        size_ft_listing,
                        size_ac_listing
                    )
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

            page += 1

        self.driver.quit()
        return self.results

    # ===================== LISTING DETAIL ===================== #

    def parse_listing(self, url, sale_type, size_ft_listing, size_ac_listing):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//span[contains(@id,'BreadCrumbs_headingTxt')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath("//span[contains(@id,'BreadCrumbs_headingTxt')]/text()")
        ))

        # ---------- DESCRIPTION ---------- #
        desc_parts = tree.xpath(
            "//table[contains(@id,'fvDescription')]//td//text()"
        )

        description = " ".join(t.strip() for t in desc_parts if t.strip())

        features = tree.xpath(
            "//div[contains(@id,'RadPageView2')]//li//text()"
        )

        if features:
            description += " " + " ".join(
                f.strip() for f in features if f.strip()
            )

        detailed_description = self._clean(description)

        # ---------- SIZE (DETAIL FALLBACK) ---------- #
        size_ft_detail, size_ac_detail = self.extract_size(detailed_description)

        size_ft = size_ft_listing or size_ft_detail
        size_ac = size_ac_listing or size_ac_detail

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(detailed_description, sale_type)

        # ---------- IMAGES ---------- #
        property_images = [
            urljoin(self.DOMAIN, img)
            for img in tree.xpath(
                "//div[contains(@class,'sp-thumbs')]//a/@href"
            )
        ]

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
        ]

        # ---------- AGENT ---------- #
        agent_name = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'accountmanager')]//h2/text()")
        ))

        agent_email = tree.xpath("//a[starts-with(@href,'mailto:')]/@href")
        agent_email = agent_email[0].replace("mailto:", "").split("?")[0] if agent_email else ""

        agent_phone = tree.xpath("//a[starts-with(@href,'tel:')]/@href")
        agent_phone = agent_phone[0].replace("tel:", "") if agent_phone else ""

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

    def normalize_sale_type_from_listing(self, text):
        t = text.lower()

        if any(k in t for k in ["to let", "rent"]):
            return "To Let"

        if any(k in t for k in ["for sale", "lease for sale"]):
            return "For Sale"

        return ""

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
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
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac\.?)',
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

        t = text.lower()

        if any(k in t for k in [
            "poa", "price on application", "upon application", "on application"
        ]):
            return ""

        if any(k in t for k in [
            "per annum", "pa", "pcm", "pw", "rent"
        ]):
            return ""

        m = re.search(r'[£]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?', t)
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

        full_pattern = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        partial_pattern = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        match = re.search(full_pattern, text)
        if match:
            return match.group().strip()

        match = re.search(partial_pattern, text)
        return match.group().strip() if match else ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""