import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class LexiconCREScraper:
    BASE_URL = "https://lexiconcre.co.uk/properties-available/"
    DOMAIN = "https://lexiconcre.co.uk"

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

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'flex_column') and contains(@class,'av_one_third')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listings = tree.xpath(
            "//div[contains(@class,'flex_column') and contains(@class,'av_one_third')]"
        )

        for item in listings:

            # ---------- BROCHURE / LISTING URL ---------- #
            brochure = item.xpath(".//a[contains(@href,'.pdf')]/@href")
            if not brochure:
                continue

            pdf_url = urljoin(self.DOMAIN, brochure[0])

            if pdf_url in self.seen_urls:
                continue
            self.seen_urls.add(pdf_url)

            # ---------- DISPLAY ADDRESS ---------- #
            display_address = self._clean(" ".join(
                item.xpath(
                    ".//section[contains(@class,'av_textblock_section')]//p[1]//text()"
                )
            ))

            # ---------- PROPERTY SUB TYPE ---------- #
            property_sub_type = self._clean(" ".join(
                item.xpath(
                    ".//h2[contains(@class,'av-special-heading-tag')]//text()"
                )
            ))

            # ---------- IMAGE ---------- #
            property_image = item.xpath(
                ".//div[contains(@class,'avia-image-container')]//img/@src"
            )
            property_image = property_image[0] if property_image else ""


            # ---------- FULL DESCRIPTION BLOCK ---------- #
            description_text = self._clean(" ".join(
                item.xpath(
                    ".//section[contains(@class,'av_textblock_section')]//p//text()"
                )
            ))

            # ---------- COMBINE DISPLAY ADDRESS + DESCRIPTION ---------- #
            combined_text = f"{display_address} {property_sub_type} {description_text}"

            # ---------- SIZE ---------- #
            size_ft, size_ac = self.extract_size(combined_text)

            # ---------- TENURE ---------- #
            tenure = self.extract_tenure(combined_text)

            # ---------- SALE TYPE ---------- #
            sale_type = self.extract_sale_type(combined_text)

            obj = {
                "listingUrl": pdf_url,
                "displayAddress": display_address,
                "price": "",
                "propertySubType": property_sub_type,
                "propertyImage": property_image,
                "detailedDescription": description_text,
                "sizeFt": size_ft,
                "sizeAc": size_ac,
                "postalCode": self.extract_postcode(display_address),
                "brochureUrl": [pdf_url],
                "agentCompanyName": "Lexicon CRE",
                "agentName": "",
                "agentCity": "",
                "agentEmail": "",
                "agentPhone": "",
                "agentStreet": "",
                "agentPostcode": "",
                "tenure": tenure,
                "saleType": sale_type,
            }

            self.results.append(obj)

        self.driver.quit()
        return self.results

    # ===================== HELPERS ===================== #


    def extract_sale_type(self, text):
        if not text:
            return ""

        t = text.lower()

        if any(x in t for x in ["for sale", "sale",'under offer']):
            return "For Sale"
        
        if any(x in t for x in ["to let", "for rent", "rent", "letting"]):
            return "To Let"

        return ""


    def extract_tenure(self, text):
        if not text:
            return ""

        t = text.lower()

        if "freehold" in t:
            return "Freehold"
        if "leasehold" in t:
            return "Leasehold"

        return ""


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

        # ===================== SQUARE FEET ===================== #
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*feet)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        # ===================== SQUARE METRES ===================== #
        if not size_ft:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(sqm|sq\.?\s*m|m2|square\s*metres|square\s*meters)',
                text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm_value = min(a, b) if b else a
                size_ft = round(sqm_value * 10.7639, 3)  # convert sqm → sqft

        # ===================== ACRES ===================== #
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac\.?)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        # ===================== HECTARES ===================== #
        if not size_ac:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(hectares?|ha)',
                text
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                hectare_value = min(a, b) if b else a
                size_ac = round(hectare_value * 2.47105, 3)  # convert ha → acres

        return size_ft, size_ac
    


    def extract_postcode(self, text):
        if not text:
            return ""

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        t = text.upper()
        m = re.search(FULL, t) or re.search(PARTIAL, t)
        return m.group() if m else ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
