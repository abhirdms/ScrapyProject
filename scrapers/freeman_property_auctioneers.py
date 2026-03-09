import re
import time
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class FreemanPropertyAuctioneersScraper:
    BASE_URL = "https://www.freemanforman.co.uk/properties/sales/most-recent-first/"
    DOMAIN = "https://www.freemanforman.co.uk"

    def __init__(self):
        self.results = []
        self.seen_urls = set()

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        service = Service("/usr/bin/chromedriver")
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"}
        )
        self.wait = WebDriverWait(self.driver, 30)

    # ===================== RUN ===================== #

    def run(self):
        page = 1

        while True:
            if page == 1:
                page_url = self.BASE_URL
            else:
                page_url = f"https://www.freemanforman.co.uk/properties/sales/most-recent-first/page-{page}"

            self.driver.get(page_url)

            try:
                self.wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "div.card--image.card--list a.card__link")
                    )
                )
            except Exception:
                break

            time.sleep(2)

            tree = html.fromstring(self.driver.page_source)

            listing_hrefs = tree.xpath(
                "//div[contains(@class,'card--image') and contains(@class,'card--list')]"
                "//div[@class='card']"
                "//a[contains(@class,'card__link')]/@href"
            )

            if not listing_hrefs:
                listing_hrefs = tree.xpath("//a[contains(@class,'card__link')]/@href")

            if not listing_hrefs:
                break

            new_found = False
            for href in listing_hrefs:
                url = urljoin(self.DOMAIN, href)

                if url in self.seen_urls:
                    continue
                self.seen_urls.add(url)
                new_found = True

                try:
                    obj = self.parse_listing(url)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

            if not new_found:
                break

            next_links = tree.xpath(
                "//a[contains(@class,'button') and contains(., 'Load more')]/@href"
            )
            if not next_links:
                break

            page += 1

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url):
        self.driver.get(url)

        try:
            self.wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "h1.details-panel__title, h1")
                )
            )
        except Exception:
            pass

        time.sleep(2)
        tree = html.fromstring(self.driver.page_source)

        # ---------- ADDRESS ---------- #
        # <span class="details-panel__title-main">Hartley Road, Cranbrook, Kent, TN17</span>
        display_address = self._first_text(tree, [
            "//span[contains(@class,'details-panel__title-main')]//text()",
            "//h1[contains(@class,'details-panel__title')]//span[1]//text()",
        ])

        # ---------- PROPERTY SUB TYPE ---------- #
        # <span class="details-panel__title-sub">3 bedroom semi-detached house for sale</span>
        property_sub_type = self._first_text(tree, [
            "//span[contains(@class,'details-panel__title-sub')]//text()",
        ])

        # ---------- PRICE ---------- #
        # <p class="details-panel__details-text-primary">£475,000</p>
        price_raw = self._first_text(tree, [
            "//p[contains(@class,'details-panel__details-text-primary')]//text()",
            "//p[contains(@class,'card__heading')]//text()",
        ])
        price = self.extract_numeric_price(price_raw)

        # ---------- SALE TYPE ---------- #
        # <p class="details-panel__details-text">Offers in excess of </p>
        sale_type_raw = self._first_text(tree, [
            "//p[contains(@class,'details-panel__details-text') and not(contains(@class,'primary'))]//text()",
        ])
        sale_type = self.normalize_sale_type(sale_type_raw) or "For Sale"

        # ---------- BEDS / BATHS / RECEPTIONS ---------- #
        # ul.details-panel__spec-list > li.details-panel__spec-list-item
        bedrooms = ""
        bathrooms = ""
        receptions = ""

        spec_items = tree.xpath(
            "//ul[contains(@class,'details-panel__spec-list')]"
            "/li[contains(@class,'details-panel__spec-list-item')]"
        )
        for item in spec_items:
            title = " ".join(item.xpath(".//title//text()")).lower()
            number = self._clean(" ".join(item.xpath(
                ".//span[contains(@class,'details-panel__spec-list-number')]//text()"
            )))
            if "bedroom" in title and not bedrooms:
                bedrooms = number
            elif "bathroom" in title and not bathrooms:
                bathrooms = number
            elif "reception" in title and not receptions:
                receptions = number

        # ---------- DESCRIPTION ---------- #
        # div.property-about-section div.copy__content p
        description_parts = tree.xpath(
            "//div[contains(@class,'property-about-section')]"
            "//div[contains(@class,'about-content-container')]//p//text()"
        )
        if not description_parts:
            description_parts = tree.xpath(
                "//div[contains(@class,'details-frame__description')]//p//text()"
            )
        detailed_description = self._clean(" ".join(description_parts))

        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- TENURE ---------- #
        # <p class="mb-0"><strong>Tenure:</strong> Freehold</p>
        tenure = ""
        tenure_nodes = tree.xpath(
            "//p[contains(@class,'mb-0') and contains(.,'Tenure')]"
        )
        if tenure_nodes:
            tenure_text = tenure_nodes[0].text_content()
            tenure_value = re.sub(r'Tenure\s*:', '', tenure_text, flags=re.IGNORECASE).strip()
            tenure = self.extract_tenure(tenure_value)
        if not tenure:
            tenure = self.extract_tenure(detailed_description)

        # ---------- IMAGES ---------- #
        # img.hero__img inside div.carousel__image-container
        raw_srcs = tree.xpath(
            "//div[contains(@class,'carousel__image-container')]//img/@src"
        )
        if not raw_srcs:
            raw_srcs = tree.xpath(
                "//img[contains(@src,'homeflow-assets') and contains(@class,'hero__img')]/@src"
            )
        property_images = []
        seen_imgs = set()
        for src in raw_srcs:
            if src.startswith("//"):
                src = "https:" + src
            if src not in seen_imgs and "homeflow-assets" in src and "photo/image" in src:
                seen_imgs.add(src)
                property_images.append(src)

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
            if "gender" not in href.lower()
        ]

        # ---------- AGENT NAME (branch) ---------- #
        # <h4 class="details-frame__content-title"> Hawkhurst</h4>
        agent_name = self._first_text(tree, [
            "//h4[contains(@class,'details-frame__content-title')]//text()",
        ])

        # ---------- AGENT ADDRESS ---------- #
        # <ul itemprop="address"> Field End High Street<br>Cranbrook<br>Kent<br>TN18 4AB </ul>
        agent_street = ""
        agent_city = ""
        agent_postcode = ""

        address_node = tree.xpath("//ul[@itemprop='address']")
        if address_node:
            addr_inner = html.tostring(address_node[0], encoding="unicode")
            # Split on <br> tags to get individual address lines
            br_parts = re.split(r'<br\s*/?>', addr_inner, flags=re.IGNORECASE)
            lines = [re.sub(r'<[^>]+>', '', p).strip() for p in br_parts]
            lines = [l for l in lines if l and l not in ('<ul', '</ul>')]
            # Remove the outer <ul ...> tag text
            lines = [l for l in lines if not l.startswith('<')]

            if lines:
                agent_street = lines[0] if len(lines) > 0 else ""
                agent_city = lines[1] if len(lines) > 1 else ""
                # Search all lines for postcode
                full_addr = " ".join(lines)
                agent_postcode = self.extract_postcode(full_addr)

        # ---------- AGENT PHONE ---------- #
        agent_phone = ""
        tel_hrefs = tree.xpath(
            "//div[contains(@class,'details-frame')]//a[contains(@href,'tel:')]/@href"
        )
        if not tel_hrefs:
            tel_hrefs = tree.xpath("//a[contains(@href,'tel:')]/@href")
        if tel_hrefs:
            agent_phone = tel_hrefs[0].replace("tel:", "").strip()

        # ---------- AGENT EMAIL ---------- #
        agent_email = ""
        mailto_hrefs = tree.xpath("//a[contains(@href,'mailto:')]/@href")
        if mailto_hrefs:
            agent_email = mailto_hrefs[0].replace("mailto:", "").strip()

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "bedrooms": bedrooms,
            "bathrooms": bathrooms,
            "receptions": receptions,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Freeman Property Auctioneers",
            "agentName": agent_name,
            "agentCity": agent_city,
            "agentEmail": agent_email,
            "agentPhone": agent_phone,
            "agentStreet": agent_street,
            "agentPostcode": agent_postcode,
            "tenure": tenure,
            "saleType": sale_type,
        }

        return obj

    # ===================== HELPERS ===================== #

    def _first_text(self, tree, xpath_list):
        """Try each XPath in order, return first non-empty joined result."""
        for xpath in xpath_list:
            result = self._clean(" ".join(tree.xpath(xpath)))
            if result:
                return result
        return ""

    def extract_size(self, text):
        if not text:
            return "", ""

        text_lower = text.lower().replace(",", "")
        text_lower = re.sub(r"[–—−]", "-", text_lower)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot)',
            text_lower
        )
        if m:
            a = float(m.group(1).replace(",", ""))
            b = float(m.group(2).replace(",", "")) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        if not size_ft:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(sqm|sq\.?\s*m\b|m2|square\s*metres?)',
                text_lower
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm = min(a, b) if b else a
                size_ft = round(sqm * 10.7639, 3)

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|ac\.?)\b',
            text_lower
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        if not size_ac:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(hectares?|ha)\b',
                text_lower
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                size_ac = round((min(a, b) if b else a) * 2.47105, 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text):
        if not text:
            return ""
        t = text.lower()
        if any(k in t for k in ["poa", "price on application", "upon application", "on application"]):
            return ""
        m = re.search(
            r'(?:£|\u00a3|&#163;)\s*(\d[\d,]*(?:\.\d+)?)(\s*[mk])?',
            text,
            re.IGNORECASE
        )
        if not m:
            return ""
        num = float(m.group(1).replace(",", ""))
        suffix = (m.group(2) or "").strip().lower()
        if suffix == "m":
            num *= 1_000_000
        elif suffix == "k":
            num *= 1_000
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

    def normalize_sale_type(self, text):
        if not text:
            return ""
        t = text.lower()
        if "for sale" in t or "sale" in t or "offers" in t or "asking" in t or "guide" in t:
            return "For Sale"
        if "to let" in t or "rent" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()).strip() if val else ""