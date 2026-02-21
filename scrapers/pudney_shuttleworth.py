import re
import time
from urllib.parse import urljoin, urlparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class PudneyShuttleworthScraper:
    BASE_URLS = [
        "https://www.pudneyshuttleworth.co.uk/in-town-retail",
        "https://www.pudneyshuttleworth.co.uk/our",
        "https://www.pudneyshuttleworth.co.uk/out-of-town-retail",
    ]
    DOMAIN = "https://www.pudneyshuttleworth.co.uk"
    AGENT_COMPANY = "Pudney Shuttleworth"

    def __init__(self):
        self.results = []
        self.seen_keys = set()

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
        for url in self.BASE_URLS:
            self.driver.get(url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//div[@role='listitem']"
                )))
            except Exception:
                continue

            self._expand_view_more()
            tree = html.fromstring(self.driver.page_source)
            items = tree.xpath("//div[@role='listitem']")

            for item in items:
                try:
                    objs = self.parse_listing(item, url)
                    if objs:
                        self.results.extend(objs)
                except Exception:
                    continue

        self.driver.quit()
        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, item, source_url):
        chunks = self._text_chunks(item)

        brochure_urls = [
            urljoin(self.DOMAIN, href)
            for href in item.xpath(".//a[contains(@href,'.pdf')]/@href")
        ]
        listing_url = brochure_urls[0] if brochure_urls else source_url

        records = self._records_from_labelled_chunks(chunks)
        if not records:
            records = [self._record_from_simple_chunks(chunks)]

        category = self.url_to_category(source_url)
        output = []

        for idx, rec in enumerate(records):
            size_text = rec.get("size_text", "")
            scheme = rec.get("scheme", "")
            location = rec.get("location", "")
            address = rec.get("address", "")
            listing_url_for_row = brochure_urls[idx] if idx < len(brochure_urls) else listing_url
            brochure_for_row = [listing_url_for_row] if listing_url_for_row else brochure_urls

            display_address = address or location
            property_sub_type = scheme or address or location
            size_ft, size_ac = self.extract_size(size_text)

            detailed_description = self._clean(
                f"Category: {category}. Scheme: {scheme}. "
                f"Location: {location}. Address: {address}. Size: {size_text}."
            )

            unique_key = "|".join([listing_url_for_row, property_sub_type, display_address, size_text])
            if unique_key in self.seen_keys:
                continue
            self.seen_keys.add(unique_key)

            obj = {
                "listingUrl": listing_url_for_row,
                "displayAddress": display_address,
                "price": "",
                "propertySubType": property_sub_type,
                "propertyImage": [],
                "detailedDescription": detailed_description,
                "sizeFt": size_ft,
                "sizeAc": size_ac,
                "postalCode": self.extract_postcode(display_address),
                "brochureUrl": brochure_for_row,
                "agentCompanyName": self.AGENT_COMPANY,
                "agentName": "",
                "agentCity": "",
                "agentEmail": "",
                "agentPhone": "",
                "agentStreet": "",
                "agentPostcode": "",
                "tenure": "",
                "saleType": "",
            }


            output.append(obj)

        return output

    # ===================== HELPERS ===================== #

    def _text_chunks(self, item):
        chunks = []
        for d in item.xpath(".//div[@data-testid='richTextElement']"):
            txt = self._clean(" ".join(d.xpath(".//text()")))
            if txt:
                chunks.append(txt)
        return chunks

    def _is_label(self, text):
        t = self._clean(text).lower().strip(":")
        return t in {"location", "address", "scheme", "size"}

    def _records_from_labelled_chunks(self, chunks):
        records = []
        current = {}
        i = 0
        n = len(chunks)

        while i < n:
            label = self._clean(chunks[i]).lower().strip(":")
            if label in {"location", "address", "scheme", "size"}:
                j = i + 1
                while j < n and self._is_label(chunks[j]):
                    j += 1
                value = chunks[j] if j < n else ""

                if value and not self._is_label(value):
                    if label == "location":
                        if current.get("location") or current.get("address") or current.get("size_text"):
                            records.append(current)
                            current = {}
                        current["location"] = value
                    elif label == "address":
                        current["address"] = value
                    elif label == "scheme":
                        current["scheme"] = value
                    elif label == "size":
                        current["size_text"] = value
                i = j + 1
                continue
            i += 1

        if current.get("location") or current.get("address") or current.get("size_text") or current.get("scheme"):
            records.append(current)

        return records

    def _record_from_simple_chunks(self, chunks):
        size_text = ""
        for c in chunks:
            if self._looks_like_size(c):
                size_text = c
                break

        values = [c for c in chunks if not self._is_label(c) and not self._looks_like_size(c)]
        scheme = values[0] if values else ""
        location = values[1] if len(values) > 1 else ""

        return {
            "scheme": scheme,
            "location": location,
            "address": "",
            "size_text": size_text,
        }

    def _expand_view_more(self):
        stagnation = 0

        while True:
            cards_before = len(self.driver.find_elements(By.XPATH, "//div[@role='listitem']"))
            btn = self._get_view_more_button()
            if not btn:
                break

            clicked = False
            try:
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                time.sleep(0.4)
                btn.click()
                clicked = True
            except Exception:
                try:
                    self.driver.execute_script("arguments[0].click();", btn)
                    clicked = True
                except Exception:
                    pass

            if not clicked:
                stagnation += 1
                if stagnation >= 2:
                    break
                continue

            loaded = False
            end_time = time.time() + 15
            while time.time() < end_time:
                time.sleep(0.6)
                cards_now = len(self.driver.find_elements(By.XPATH, "//div[@role='listitem']"))
                if cards_now > cards_before:
                    loaded = True
                    break

                # If button disappeared, we've reached the final page.
                if not self._get_view_more_button():
                    loaded = True
                    break

            if loaded:
                stagnation = 0
                continue

            stagnation += 1
            if stagnation >= 2:
                break

    def _get_view_more_button(self):
        buttons = self.driver.find_elements(
            By.XPATH,
            "//button[normalize-space()='View More' or .//span[normalize-space()='View More']]"
        )
        for btn in buttons:
            try:
                if btn.is_displayed() and btn.is_enabled():
                    return btn
            except Exception:
                continue
        return None

    def _looks_like_size(self, text):
        t = text.lower()
        return bool(re.search(r"\b(sq\.?\s*ft|sqft|sq\s*ft|sf|acres?|acre)\b", t))

    def url_to_category(self, url):
        path = urlparse(url).path.strip("/").replace("-", " ")
        return " ".join(w.capitalize() for w in path.split()) if path else ""

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
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac)',
            text
        )
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        return size_ft, size_ac

    def extract_postcode(self, text):
        if not text:
            return ""

        full = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        partial = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        t = text.upper()
        m = re.search(full, t) or re.search(partial, t)
        return m.group() if m else ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""
