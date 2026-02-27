import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from lxml import html


class FludePropertyConsultantsScraper:
    BASE_URL = "https://www.flude.com/Property/Search/All/All/All/Both"
    DOMAIN = "https://www.flude.com"

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

        self.detail_driver = webdriver.Chrome(service=service, options=chrome_options)
        self.detail_wait = WebDriverWait(self.detail_driver, 20)

    # ===================== RUN ===================== #

    def run(self):
        self.driver.get(self.BASE_URL)

        try:
            self.wait.until(EC.presence_of_element_located((
                By.XPATH,
                "//div[contains(@class,'property-card-wrapper')]//div[contains(@class,'property-card')]",
            )))
        except Exception:
            self.driver.quit()
            self.detail_driver.quit()
            return self.results

        while True:
            tree = html.fromstring(self.driver.page_source)
            cards = tree.xpath("//div[contains(@class,'property-card-wrapper')]//div[contains(@class,'property-card')]")

            if not cards:
                break

            for card in cards:
                href = self._clean("".join(card.xpath(
                    ".//a[contains(@class,'property-card-image') or contains(@class,'property-card-button')][contains(@href,'/property/details/')][1]/@href"
                )))
                if not href:
                    continue

                listing_url = urljoin(self.DOMAIN, href)
                if listing_url in self.seen_urls:
                    continue
                self.seen_urls.add(listing_url)

                listing_summary = {
                    "address": self._clean(" ".join(card.xpath(".//div[contains(@class,'property-card-address')]//text()"))),
                    "property_type": self._clean(" ".join(card.xpath(".//div[contains(@class,'property-card-type')]//text()"))),
                    "size_text": self._clean(" ".join(card.xpath(".//div[contains(@class,'property-card-size')]//text()"))),
                    "status_text": self._clean(" ".join(card.xpath(".//div[contains(@class,'property-status')]//text()"))),
                    "image_style": self._clean("".join(card.xpath(".//a[contains(@class,'property-card-image')]/@style"))),
                }

                try:
                    obj = self.parse_listing(listing_url, listing_summary)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    continue

            current_first_href = self._clean("".join(tree.xpath(
                "(//div[contains(@class,'property-card-wrapper')]//a[contains(@href,'/property/details/')][1]/@href)"
            )))
            current_first_url = urljoin(self.DOMAIN, current_first_href) if current_first_href else ""

            try:
                next_li = self.driver.find_element(
                    By.XPATH,
                    (
                        "(//ul[contains(@class,'pagination')]"
                        "//button[contains(@class,'pagination-arrows') and @aria-label='Next']"
                        "/ancestor::li[1])[1]"
                    ),
                )
            except Exception:
                break

            next_classes = (next_li.get_attribute("class") or "").lower()
            if "disabled" in next_classes:
                break

            try:
                next_btn = next_li.find_element(
                    By.XPATH,
                    ".//button[contains(@class,'pagination-arrows') and @aria-label='Next']",
                )
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", next_btn)
                self.driver.execute_script("arguments[0].click();", next_btn)

                self.wait.until(lambda d: (
                    urljoin(
                        self.DOMAIN,
                        self._clean("".join(html.fromstring(d.page_source).xpath(
                            "(//div[contains(@class,'property-card-wrapper')]//a[contains(@href,'/property/details/')][1]/@href)"
                        )))
                    ) != current_first_url
                ))
            except Exception:
                break

        self.driver.quit()
        self.detail_driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url, listing_summary):
        self.detail_driver.get(url)

        self.detail_wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//div[contains(@class,'property-details-page-wrapper')]",
        )))

        tree = html.fromstring(self.detail_driver.page_source)

        display_address = self._clean(" ".join(
            tree.xpath("//h2[contains(@class,'property-address')]//text()")
        )) or listing_summary.get("address", "")

        property_sub_type = self._clean(" ".join(
            tree.xpath("//h3[contains(@class,'property-type')]//text()")
        )) or listing_summary.get("property_type", "")

        status_text = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'property-status-wrapper')]//h1//text()")
        )) or listing_summary.get("status_text", "")

        size_text = self._clean(" ".join(
            tree.xpath("//h3[contains(@class,'property-size')]//text()")
        )) or listing_summary.get("size_text", "")

        section_parts = []
        for title in tree.xpath("//div[contains(@class,'property-details-section')]//p[contains(@class,'property-details-title')]"):
            heading = self._clean(" ".join(title.xpath(".//text()")))
            content = self._clean(" ".join(
                title.xpath("following-sibling::p[contains(@class,'property-details-content')][1]//text()")
            ))
            if heading and content:
                section_parts.append(f"{heading}: {content}")
            elif content:
                section_parts.append(content)

        features_text = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'property-key-features')]//li//text()")
        ))
        if features_text:
            section_parts.append(features_text)

        detailed_description = self._clean(" ".join(
            p for p in [size_text] + section_parts if p
        ))

        sale_type = self.normalize_sale_type(" ".join([status_text, detailed_description]))
        size_ft, size_ac = self.extract_size(detailed_description)
        tenure = self.extract_tenure(detailed_description)
        price = self.extract_numeric_price(detailed_description, sale_type)

        property_images = []
        style_chunks = tree.xpath("//div[contains(@class,'property-image')]/@style")
        for style in style_chunks:
            for image_url in re.findall(r"url\(['\"]?([^'\")]+)", style):
                full = urljoin(self.DOMAIN, image_url)
                if "flude-logo-large-background.jpg" in full:
                    continue
                if full not in property_images:
                    property_images.append(full)

        if not property_images:
            fallback_image = self.extract_image_from_style(listing_summary.get("image_style", ""))
            if fallback_image:
                property_images.append(urljoin(self.DOMAIN, fallback_image))

        brochure_urls = []
        for href in tree.xpath("//a[contains(@href,'ViewFile') or contains(translate(@href,'PDF','pdf'),'.pdf')]/@href"):
            full = urljoin(self.DOMAIN, href)
            if full not in brochure_urls:
                brochure_urls.append(full)

        agent_name = self._clean(" ".join(
            tree.xpath("(//div[contains(@class,'property-agent')]//p[contains(@class,'property-agent-name')]//text())[1]")
        ))
        agent_phone = self._clean("".join(
            tree.xpath("(//div[contains(@class,'property-agent')]//a[contains(@class,'property-agent-tel')]/@href)[1]")
        )).replace("tel:", "", 1)
        agent_email = self._clean("".join(
            tree.xpath("(//div[contains(@class,'property-agent')]//a[contains(@class,'property-agent-email')]/@href)[1]")
        )).replace("mailto:", "", 1)

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
            "agentCompanyName": "Flude Property Consultants",
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

    def extract_image_from_style(self, style_text):
        if not style_text:
            return ""
        matches = re.findall(r"url\(['\"]?([^'\")]+)", style_text)
        for value in matches:
            if "flude-logo-large-background.jpg" not in value:
                return value
        return matches[0] if matches else ""

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
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(sq\.?\s*ft\.?|sqft|sf|square\s*feet|square\s*foot|sq\s*feet)",
            text,
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        if not size_ft:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
                r"(sqm|sq\.?\s*m|m2|square\s*metres|square\s*meters)",
                text,
            )
            if m:
                a = float(m.group(1))
                b = float(m.group(2)) if m.group(2) else None
                sqm_value = min(a, b) if b else a
                size_ft = round(sqm_value * 10.7639, 3)

        m = re.search(
            r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
            r"(acres?|acre|ac\.?)",
            text,
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        if not size_ac:
            m = re.search(
                r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*"
                r"(hectares?|ha)",
                text,
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

        if any(k in t for k in [
            "per annum", "pa", "per year", "pcm", "per month", "pw", "per week", "rent"
        ]):
            return ""

        m = re.search(r"[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?", t)
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
        full_pattern = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b"
        partial_pattern = r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\b"

        match = re.search(full_pattern, text)
        if match:
            return match.group().strip()

        match = re.search(partial_pattern, text)
        return match.group().strip() if match else ""

    def normalize_sale_type(self, text):
        t = (text or "").lower()
        if "for sale" in t or "sale" in t:
            return "For Sale"
        if "to let" in t or "rent" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
