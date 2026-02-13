import re
import requests
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class HoughGouldScraper:

    BASE_URL = "https://houghgould.com/property-listings/"
    DOMAIN = "https://houghgould.com"
    AGENT_COMPANY = "Hough Gould"

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
        self.wait = WebDriverWait(self.driver, 30)

    # ======================================================
    # RUN
    # ======================================================

    def run(self):

        self.driver.get(self.BASE_URL)

        self.wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//div[contains(@class,'wpgmaps_mlist_row')]")
            )
        )

        tree = html.fromstring(self.driver.page_source)

        listings = tree.xpath("//div[contains(@class,'wpgmaps_mlist_row')]")

        for listing in listings:
            data = self.parse_listing(listing)
            if data and data["listingUrl"] not in self.seen_urls:
                self.seen_urls.add(data["listingUrl"])
                self.results.append(data)

        self.driver.quit()
        return self.results

    # ======================================================
    # PARSE LISTING
    # ======================================================

    def parse_listing(self, listing):

        display_address = self.clean(
            " ".join(
                listing.xpath(".//div[contains(@class,'wpgmza-address')]/text()")
            )
        )

        description = self.clean(
            " ".join(
                listing.xpath(".//div[contains(@class,'wpgmza-desc')]//text()")
            )
        )

        sale_type = "To Let" if "TO LET" in display_address.upper() else "For Sale"

        images = listing.xpath(
            ".//div[contains(@class,'wpgmza-gallery-container')]//img/@src"
        )

        images = [
            urljoin(self.DOMAIN, img.strip())
            for img in images
            if img.strip()
        ]

        # --- Get Downloads Page Link ---
        brochure_pages = listing.xpath(
            ".//div[contains(@class,'wpgmza-link')]//a/@href"
        )

        brochure_pages = [
            urljoin(self.DOMAIN, link.strip())
            for link in brochure_pages
            if link.strip()
        ]

        # --- Extract PDF Links from Downloads Page ---
        pdf_links = []
        for page_url in brochure_pages:
            pdf_links.extend(self.extract_brochure_pdfs(page_url))

        pdf_links = list(set(pdf_links))

        # ---- YOUR NORMALIZATION FUNCTIONS ----
        size_ft, size_ac = extract_size(description)
        postcode = extract_postcode(description)
        tenure = extract_tenure(description)


        obj = {
            "listingUrl": pdf_links[0] if pdf_links else "",
            "displayAddress": display_address,
            "price": "",
            "propertySubType": "",
            "propertyImage": images,
            "detailedDescription": description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": postcode,
            "brochureUrl": pdf_links,
            "agentCompanyName": self.AGENT_COMPANY,
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

    # ======================================================
    # EXTRACT PDF LINKS FROM DOWNLOAD PAGE
    # ======================================================

    def extract_brochure_pdfs(self, download_page_url):

        HEADERS = {"User-Agent": "Mozilla/5.0"}

        try:
            r = requests.get(download_page_url, headers=HEADERS, timeout=30)
            r.raise_for_status()
        except:
            return []

        tree = html.fromstring(r.text)

        pdf_links = tree.xpath(
            "//div[contains(@class,'et_pb_blurb')]"
            "//a[contains(@href,'.pdf')]/@href"
        )

        pdf_links = [
            urljoin(download_page_url, link.strip())
            for link in pdf_links
            if link.strip().lower().endswith(".pdf")
        ]

        return list(set(pdf_links))

    def clean(self, value):
        return value.strip() if value else ""


# ======================================================
# YOUR EXACT FUNCTIONS (UNCHANGED)
# ======================================================

def extract_postcode(text: str):
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


def extract_tenure(text: str):
    if not text:
        return ""
    
    t = text.lower()

    if "freehold" in t:
        return "Freehold"

    if "leasehold" in t:
        return "Leasehold"

    return ""


def extract_size(text: str):

    if not text:
        return "", ""

    SQM_TO_SQFT = 10.7639
    HECTARE_TO_ACRE = 2.47105

    text = text.lower().replace(",", "")
    text = re.sub(r"[–—−]", "-", text)

    size_ft = ""
    size_ac = ""

    m = re.search(
        r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\.?\s*ft\.?|sqft|sf)\b',
        text
    )

    if m:
        a = float(m.group(1))
        b = float(m.group(2)) if m.group(2) else None
        size_ft = round(min(a, b), 3) if b else round(a, 3)
        return size_ft, size_ac

    m = re.search(
        r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sqm|m2|m²)\b',
        text
    )
    if m:
        a = float(m.group(1))
        b = float(m.group(2)) if m.group(2) else None
        val = min(a, b) if b else a
        size_ft = round(val * SQM_TO_SQFT, 3)
        return size_ft, size_ac

    m = re.search(
        r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac)\b',
        text
    )
    if m:
        a = float(m.group(1))
        b = float(m.group(2)) if m.group(2) else None
        size_ac = round(min(a, b), 3) if b else round(a, 3)
        return size_ft, size_ac

    m = re.search(
        r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(hectares?|hectare|ha)\b',
        text
    )
    if m:
        a = float(m.group(1))
        b = float(m.group(2)) if m.group(2) else None
        val = min(a, b) if b else a
        size_ac = round(val * HECTARE_TO_ACRE, 3)
        return size_ft, size_ac

    return size_ft, size_ac
