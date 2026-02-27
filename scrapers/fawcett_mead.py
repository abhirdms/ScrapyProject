import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class FawcettMeadScraper:
    BASE_URL = "https://fmx.co.uk/our-properties/"
    DOMAIN = "https://fmx.co.uk"

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
        current_page = 1

        while True:
            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'jet-listing-grid__item')]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)
            listing_blocks = tree.xpath("//div[contains(@class,'jet-listing-grid__item')]")

            if not listing_blocks:
                break

            page_cards = []
            for block in listing_blocks:
                href = block.xpath(
                    ".//a[contains(@class,'jet-engine-listing-overlay-link')]/@href"
                )
                if not href:
                    continue

                url = urljoin(self.DOMAIN, href[0])

                if url in self.seen_urls:
                    continue
                self.seen_urls.add(url)

                # ✅ SALE TYPE FROM LISTING PAGE
                sale_type_raw = self._clean(self._first_or_empty(
                    block.xpath(".//h2[contains(@class,'elementor-heading-title')]/text()")
                ))
                sale_type = self.normalize_sale_type(sale_type_raw)

                listing_fields = [
                    self._clean(x) for x in block.xpath(
                        ".//div[contains(@class,'jet-listing-dynamic-field__content')]/text()"
                    ) if self._clean(x)
                ]
                listing_town = listing_fields[0] if len(listing_fields) > 0 else ""
                listing_title = listing_fields[1] if len(listing_fields) > 1 else ""

                listing_status = self._clean(self._first_or_empty(
                    block.xpath(
                        ".//div[contains(@class,'e-con-inner')][.//div[normalize-space()='Status:']]"
                        "//div[contains(@class,'elementor-heading-title') and normalize-space()!='Status:']/text()"
                    )
                ))

                page_cards.append({
                    "url": url,
                    "sale_type": sale_type,
                    "listing_town": listing_town,
                    "listing_title": listing_title,
                    "listing_status": listing_status,
                })

            for card in page_cards:
                try:
                    obj = self.parse_listing(
                        url=card["url"],
                        sale_type=card["sale_type"],
                        listing_town=card["listing_town"],
                        listing_title=card["listing_title"],
                        listing_status=card["listing_status"],
                    )
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

            pages_attr = self._first_or_empty(
                tree.xpath("(//div[contains(@class,'jet-listing-grid__items')])[1]/@data-pages")
            )
            total_pages = int(pages_attr) if pages_attr and pages_attr.isdigit() else current_page

            if current_page >= total_pages:
                break

            next_page = current_page + 1
            self.driver.get(self.BASE_URL)
            if not self._go_to_results_page(next_page):
                break
            current_page = next_page

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url, sale_type, listing_town="", listing_title="", listing_status=""):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h1[contains(@class,'elementor-heading-title')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- TOWN ---------- #
        town = self._clean(" ".join(
            tree.xpath(
                "(//div[contains(@class,'jet-listing-dynamic-field__content')])[1]/text()"
            )
        ))
        if not town:
            town = listing_town

        # ---------- DISPLAY ADDRESS ---------- #
        display_address = self._clean(" ".join(
            tree.xpath(
                "//i[contains(@class,'fa-map-marker-alt')]"
                "/following-sibling::div/text()"
            )
        ))
        if not display_address:
            display_address = ", ".join(
                [v for v in [listing_title, listing_town] if v]
            )

        # ---------- DESCRIPTION ---------- #
        location_text = self.get_section_text(tree, "Location")
        description_text = self.get_section_text(tree, "Description")

        detailed_description = " ".join(
            part for part in [location_text, description_text] if part
        )

        # ---------- SIZE ---------- #
        size_ft, size_ac = self.extract_size(detailed_description)

        # ---------- TENURE ---------- #
        tenure = self.extract_tenure(detailed_description)

        # ---------- PRICE ---------- #
        price = self.extract_numeric_price(detailed_description, sale_type)

        # ---------- IMAGES (DEDUP) ---------- #
        images = tree.xpath(
            "//div[contains(@class,'jet-woo-product-gallery__image-item')]"
            "//img[contains(@class,'wp-post-gallery')]/@src"
        )
        property_images = list(dict.fromkeys(images))

        # ---------- BROCHURE ---------- #
        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in tree.xpath(
                "//h4[normalize-space()='Downloads']"
                "/following::div[contains(@class,'jet-listing-dynamic-field__content')]"
                "//a[contains(@href,'.pdf')]/@href"
            )
        ]

        # ---------- AGENT DETAILS ---------- #
        agent_name = ""
        agent_phone = ""
        agent_email = ""

        contact_blocks = tree.xpath(
            "//h4[normalize-space()='Contacts for this scheme']"
            "/following::div[contains(@class,'jet-listing-grid__item')]"
        )

        if contact_blocks:
            first = contact_blocks[0]

            # Name (first dynamic field only)
            name = first.xpath(
                ".//div[contains(@class,'jet-listing-dynamic-field__content')][1]/text()"
            )

            # Phone (extract from text using regex)
            phone_text = " ".join(
                first.xpath(
                    ".//div[contains(@class,'jet-listing-dynamic-field__content')]/text()"
                )
            )

            email = first.xpath(
                ".//a[starts-with(@href,'mailto:')]/@href"
            )

            agent_name = self._clean(" ".join(name))
            agent_phone = self.extract_phone(phone_text)
            agent_email = email[0].replace("mailto:", "").strip() if email else ""

        if not sale_type and listing_status:
            sale_type = self.normalize_sale_type(listing_status)

        # ---------- POSTCODE (ADDRESS + DESCRIPTION FALLBACK) ---------- #
        postcode = self.extract_postcode(display_address)
        if not postcode:
            postcode = self.extract_postcode(detailed_description)

        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "Scheme",
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": postcode,
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Fawcett Mead",
            "agentName": agent_name,
            "agentCity": town,
            "agentEmail": agent_email,
            "agentPhone": agent_phone,
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": tenure,
            "saleType": sale_type,
        }


        return obj

    # ===================== HELPERS ===================== #

    def get_section_text(self, tree, heading):
        return self._clean(" ".join(
            tree.xpath(
                f"//h3[contains(translate(normalize-space(),"
                "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),"
                f"'{heading.lower()}')]"
                "/following-sibling::p//text()"
            )
        ))

    def extract_phone(self, text):
        if not text:
            return ""
        m = re.search(r'(\+?\d[\d\s().-]{7,}\d)', text)
        return self._clean(m.group(1)) if m else ""

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(sq\.?\s*ft|sqft|sf|square\s*feet)',
            text
        )
        if m:
            size_ft = round(float(m.group(1)), 3)

        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(acres?|acre|ac)',
            text
        )
        if m:
            size_ac = round(float(m.group(1)), 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale":
            return ""

        if not text:
            return ""

        t = text.lower()

        if any(k in t for k in [
            "poa", "price on application", "upon application", "on application"
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
        if "sale" in t or "investment" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""

    def _first_or_empty(self, values):
        return values[0] if values else ""

    def _go_to_results_page(self, next_page):
        button_xpath = (
            "//div[contains(@class,'jet-filters-pagination__item')"
            f" and @data-value='{next_page}']"
        )
        grid_xpath = "(//div[contains(@class,'jet-listing-grid__items')])[1]"

        try:
            button = self.wait.until(EC.element_to_be_clickable((By.XPATH, button_xpath)))
            self.driver.execute_script("arguments[0].click();", button)

            self.wait.until(
                lambda d: d.find_element(By.XPATH, grid_xpath).get_attribute("data-page") == str(next_page)
            )
            self.wait.until(EC.presence_of_element_located((
                By.XPATH,
                f"{grid_xpath}//div[contains(@class,'jet-listing-grid__item')]"
            )))
            return True
        except Exception:
            return False
