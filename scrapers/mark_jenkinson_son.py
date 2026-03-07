import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class MarkJenkinsonSonScraper:
    BASE_URL = "https://www.markjenkinson.co.uk/agency-properties"
    DOMAIN = "https://www.markjenkinson.co.uk"

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
            page_url = self.BASE_URL if page == 1 else f"{self.BASE_URL}/page/{page}"
            self.driver.get(page_url)

            try:
                self.wait.until(EC.presence_of_all_elements_located((
                    By.XPATH,
                    "//div[contains(@class,'grid')]/div[contains(@class,'h-full')]"
                )))
            except:
                break

            # ===== EXTRACT ALL CARD DATA FROM PAGE SOURCE (not live elements) =====
            tree = html.fromstring(self.driver.page_source)
            card_nodes = tree.xpath(
                "//div[contains(@class,'grid')]/div[contains(@class,'h-full')]"
            )


            if not card_nodes:
                break

            # Collect lightweight dicts from the listing page — no navigation yet
            card_data_list = []
            for card in card_nodes:
                # ===== URL =====
                hrefs = card.xpath(".//a[contains(@href,'/property/')]/@href")
                if not hrefs:
                    continue
                listing_url = urljoin(self.DOMAIN, hrefs[0])

                if listing_url in self.seen_urls:
                    continue
                self.seen_urls.add(listing_url)

                # ===== ADDRESS =====
                display_address = self._clean(" ".join(
                    card.xpath(".//div[contains(@class,'uppercase')]//a//text()")
                ))

                # ===== PRICE =====
                price_text = self._clean(" ".join(
                    card.xpath(".//p[contains(@class,'font-bold')]//span//text()")
                ))

                # ===== IMAGES =====
                listing_images = list(dict.fromkeys([
                    urljoin(self.DOMAIN, src)
                    for src in card.xpath(".//img[contains(@src,'property-images')]/@src")
                    if src
                ]))

                card_data_list.append({
                    "url": listing_url,
                    "address": display_address,
                    "price_text": price_text,
                    "images": listing_images,
                })

            # ===== NOW VISIT EACH DETAIL PAGE =====
            added_on_page = 0
            for card_data in card_data_list:
                try:
                    obj = self.parse_listing(
                        url=card_data["url"],
                        listing_status_text=card_data["price_text"],
                        listing_address=card_data["address"],
                        listing_price_text=card_data["price_text"],
                        listing_images=card_data["images"],
                    )
                    if obj:
                        self.results.append(obj)
                        added_on_page += 1
                except Exception:
                    continue

            if added_on_page == 0 and page > 1:
                break

            # ===== CHECK IF NEXT PAGE EXISTS =====
            # Go back to the listing page to check for a next-page link
            self.driver.get(page_url)
            try:
                self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            except:
                pass

            next_page_tree = html.fromstring(self.driver.page_source)
            next_links = next_page_tree.xpath(
                f"//a[contains(@href,'/agency-properties/page/{page + 1}')]"
            )
            if not next_links:
                break

            page += 1

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(
            self,
            url,
            listing_status_text="",
            listing_address="",
            listing_price_text="",
            listing_images=None,
        ):
            self.driver.get(url)
            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))

            tree = html.fromstring(self.driver.page_source)

            display_address = listing_address
            price_text = listing_price_text
            property_images = listing_images or []

            # ===== ADDRESS FALLBACK =====
            if not display_address:
                display_address = self._clean(" ".join(tree.xpath("//h1//text()")))

            # ===== PAGE TEXT =====
            page_text = self._clean(tree.xpath("string(//body)"))

            sale_type = self.normalize_sale_type(
                " ".join([listing_status_text, price_text, page_text])
            )

            # ===== PRICE FALLBACK =====
            if not price_text:
                price_text = self._clean(" ".join(
                    tree.xpath("//*[contains(text(),'£')]//text()")
                ))

            price = self.extract_numeric_price(price_text, sale_type)

            # ===== PROPERTY SUBTYPE =====
            property_sub_type = self._clean(" ".join(
                tree.xpath("(//div[contains(@class,'font-bold')])[1]//text()")
            ))

            # ===== DESCRIPTION =====
            detailed_description = self._clean(" ".join(
                tree.xpath("//div[contains(@class,'cms-content')]//text()")
            ))

            # ===== SIZE / TENURE =====
            size_ft, size_ac = self.extract_size(detailed_description)
            tenure = self.extract_tenure(detailed_description)

            # ===== DETAIL IMAGES =====
            detail_images = [
                urljoin(self.DOMAIN, href.strip())
                for href in tree.xpath("//a[contains(@href,'property-images')]/@href")
                if href and href.strip()
            ]
            property_images = list(dict.fromkeys(property_images + detail_images))

            # ===== BROCHURES =====
            # Exclude site-wide generic PDFs that appear on every page
            GENERIC_PDFS = {
                "additional-non-optional-fees-and-cost-guidance.pdf",
                "terms-of-bidding.pdf",
            }
            brochure_urls = list(dict.fromkeys([
                urljoin(self.DOMAIN, href.strip())
                for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
                if href and href.strip()
                and not any(generic in href for generic in GENERIC_PDFS)
            ]))

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
                "agentCompanyName": "Mark Jenkinson & Son",
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

    def is_sold_or_unavailable(self, text):
        if not text:
            return False
        t = text.lower()
        return any(k in t for k in ["sold", "withdrawn"])

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

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*feet)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

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
                size_ft = round(sqm_value * 10.7639, 3)

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

        m = re.search(r'[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?', t)
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
        t = text.lower()
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""