import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class GvpropertyScraper:
    BASE_URL = "https://www.gvproperty.co.uk/property-search/"
    DOMAIN = "https://www.gvproperty.co.uk/"

    def __init__(self):
        self.results = []

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        service = Service("/usr/bin/chromedriver")

        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 20)

    # ---------------- RUN ---------------- #

    def run(self):
        self.driver.get(self.BASE_URL)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'psp_result')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        listing_urls = tree.xpath(
            "//div[contains(@class,'psp_result')]/a[@class='psp_result__url']/@href"
        )

        for rel_url in listing_urls:
            try:
                url = urljoin(self.DOMAIN, rel_url)
                self.results.append(self.parse_listing(url))
            except Exception:
                continue

        self.driver.quit()
        return self.results

    # ---------------- LISTING ---------------- #

    def parse_listing(self, url):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h1[contains(@class,'psp_single__title')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        display_address = self._clean(" ".join(
            tree.xpath(
                "//h1[@class='psp_single__title']/text() | "
                "//h1[@class='psp_single__title']/span[@class='adressspan']/text() | "
                "//h1[@class='psp_single__title']/span[@class='text-nowrap']/text()"
            )
        ))

        detailed_description = self._clean(" ".join(
            tree.xpath(
                "//h3[text()='Description']"
                "/ancestor::div[contains(@class,'wpb_column')]//ul//text()"
            )
        ))

        size_ft, size_ac = self.extract_size(
            text=" ".join(
                tree.xpath("//h1[contains(@class,'psp_single__title')]/following::h3[2]/text()")
            )
        )

        headline_text = " ".join(
                t.strip()
                for t in tree.xpath("//div[contains(@class,'nectar-split-heading')]//text()[normalize-space()]")
            )
                    
        if not size_ac:
            _, size_ac = self.extract_size(text=headline_text)

        if not size_ac:
            _, size_ac = self.extract_size(text=detailed_description)

        sale_type = self.get_sale_type(tree)


        obj = {
            "listingUrl": url,
            "displayAddress": display_address,

            "price": self.extract_numeric_price(
                " ".join(
                    tree.xpath(
                        "//div[@class='nectar-icon-list-item']"
                        "/div[@class='content'][h4[text()='Quoting Rent']]"
                        "/text()[normalize-space()]"
                    )
                ),
                sale_type
            ),

            "propertySubType": self._clean(" ".join(
                tree.xpath("//div[@class='property-data2']/p[@class='prop_type']/text()")
            )),

            "propertyImage": [
                urljoin(self.DOMAIN, img)
                for img in tree.xpath(
                    "//div[@id='tab-gallery']"
                    "//div[contains(@class,'cell')]//img/@src"
                )
            ],

            "detailedDescription": detailed_description,

            "sizeFt": size_ft,
            "sizeAc": size_ac,

            "postalCode": self.extract_postcode(
                " ".join(tree.xpath("//span[@class='text-nowrap']/text()"))
            ),

            "brochureUrl": self.get_brochure_url(tree),

            "agentCompanyName": "GV&Co",

            "agentName": self._clean(" ".join(
                tree.xpath(
                    "(//div[contains(@class,'vc_contact')])[1]//h3/strong/text()"
                )
            )),

            "agentCity": "",
            "agentEmail": self._clean(" ".join(
                tree.xpath(
                    "(//div[contains(@class,'vc_contact')])[1]"
                    "//a[starts-with(@href,'mailto:')]/text()"
                )
            )),

            "agentPhone": self.extract_first_phone(
                " ".join(
                    tree.xpath(
                        "(//div[contains(@class,'vc_contact')])[1]//p/text()"
                    )
                )
            ),

            "agentStreet": "",
            "agentPostcode": "",

            "tenure": self.get_tenure_from_description(detailed_description),


            "saleType": sale_type,

        }

        return obj

    # ---------------- HELPERS ---------------- #

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower()

        combined_text = (
            str(text)
            .replace("m²", "m2")
            .replace("㎡", "m2")
            .replace(",", "")
            .strip()
        )

        combined_text = re.sub(r"[–—−]", "-", combined_text)

        size_ft = ""
        size_ac = ""

        # ---------- SQ FT RANGE ----------
        sqft_range_pattern = (
            r'(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*'
            r'(sq\.?\s*ft|sqft|square\s*feet|sf)'
        )
        m = re.search(sqft_range_pattern, combined_text)
        if m:
            size_ft = int(min(float(m.group(1)), float(m.group(2))))

        # ---------- SQ FT SINGLE ----------
        if not size_ft:
            sqft_single_pattern = (
                r'(\d+(?:\.\d+)?)\s*(sq\.?\s*ft|sqft|square\s*feet|sf)'
            )
            m = re.search(sqft_single_pattern, combined_text)
            if m:
                size_ft = int(float(m.group(1)))

        # ---------- SQ METERS → SQ FT ----------
        if not size_ft:
            sqm_pattern = (
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(sqm|sq\.?\s*m|m2|square\s*met(?:er|re)s)'
            )
            m = re.search(sqm_pattern, combined_text)
            if m:
                start = float(m.group(1)) * 10.7639
                end = float(m.group(2)) * 10.7639 if m.group(2) else None
                size_ft = int(min(start, end)) if end else int(start)

        # ---------- ACRES ----------
        acre_pattern = (
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac)'
        )
        m = re.search(acre_pattern, combined_text)
        if m:
            start = float(m.group(1))
            end = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(start, end) if end else start, 3)

        # ---------- HECTARES → ACRES ----------
        if not size_ac:
            hectare_pattern = (
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(hectares?|ha)'
            )
            m = re.search(hectare_pattern, combined_text)
            if m:
                start = float(m.group(1)) * 2.47105
                end = float(m.group(2)) * 2.47105 if m.group(2) else None
                size_ac = round(min(start, end) if end else start, 3)

        return size_ft, size_ac





    def extract_first_phone(self, text):
        """
        Extract only the FIRST phone number from text.
        Supports UK landline & mobile formats.
        """
        if not text:
            return ""

        # Normalize spaces
        raw = re.sub(r"\s+", " ", text)

        # UK phone patterns
        phones = re.findall(
            r'\b(?:0\d{2,4}\s?\d{3}\s?\d{3,4}|07\d{3}\s?\d{6})\b',
            raw
        )

        return phones[0] if phones else ""


    def get_brochure_url(self, tree):
        """
        Extract actual brochure PDF URL from brochure tab.
        """
        urls = tree.xpath(
            "//div[@id='tab-brochure']//a[contains(@href,'.pdf')]/@href"
        )

        if not urls:
            return ""

        return self.normalize_url(urls[0])


    def get_sale_type(self, tree):
        """
        Validates and normalises sale type.
        Allowed values:
        - For Sale
        - To Let
        """
        raw = " ".join(
            tree.xpath("//span[contains(@class,'psp_single__subtitle')]/text()")
        )

        if not raw:
            return ""

        raw = raw.lower()

        if "for sale" in raw:
            return "For Sale"

        if "to let" in raw:
            return "To Let"

        return ""


    def extract_postcode(self, text):
        if not text:
            return ""

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        text = text.upper()
        m = re.search(FULL, text) or re.search(PARTIAL, text)
        return m.group().strip() if m else ""

    def normalize_url(self, url):
        return urljoin(self.DOMAIN, url) if url else ""
    
    def extract_numeric_price(self, text, sale_type):
        """
        Extract numeric price ONLY if sale_type == 'For Sale'

        Handles:
        - £250,000
        - £250,000 - £300,000
        - POA / On Application
        """
        if not text:
            return ""

        if not sale_type or sale_type.lower() != "for sale":
            return ""

        raw = text.lower()

        if any(k in raw for k in [
            "poa",
            "price on application",
            "on application",
            "upon application",
            "subject to contract"
        ]):
            return ""

        raw = raw.replace("£", "").replace(",", "")
        raw = re.sub(r"(to|–|—)", "-", raw)

        numbers = re.findall(r"\d+(?:\.\d+)?", raw)
        if not numbers:
            return ""

        price = min(float(n) for n in numbers)
        return str(int(price)) if price.is_integer() else str(price)

    
    def get_tenure_from_description(self, text):
        """
        Detect tenure type from description.
        Supported:
        - Freehold
        - Leasehold
        """
        if not text:
            return ""

        raw = text.lower()

        if "leasehold" in raw:
            return "Leasehold"

        if "freehold" in raw:
            return "Freehold"

        return ""



    def _clean(self, val):
        return val.strip() if val else ""
