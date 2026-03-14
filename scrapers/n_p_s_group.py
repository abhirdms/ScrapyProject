import re
import time
import requests
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class NPSGroupScraper:
    """
    How the NPS website actually works (verified):
    ─────────────────────────────────────────────
    • /searchproperties/                                   → home page (no listings)
    • /searchproperties/Include-Inactive/Units/{Type}/     → listing grid, rendered by JS/ASP.NET
      Pagination: ?paging=true&page=N appended to the category URL
    • /propertyInfo/{id}/{slug}                            → detail page, renders with plain requests
                                                             (no JS required)
    Strategy:
      1. Use Selenium only for the listing grid pages (JS-rendered).
      2. Use requests + lxml for detail pages (static HTML, much faster).
    """

    DOMAIN = "https://property.nps.co.uk"

    # All known category slugs from the site's home page
    CATEGORIES = [
        "Industrial",
        "Retail",
        "Development",
        "Residential",
        "Land",
        "Office",
    ]

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    }

    def __init__(self):
        self.results   = []
        self.seen_urls = set()
        self.session   = requests.Session()
        self.session.headers.update(self.HEADERS)

        chrome_options = Options()
        # chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])

        # service = Service("/usr/bin/chromedriver")
        service = Service("C:/Users/educa/Downloads/ScrapyProject/ScrapyProject/chromedriver.exe")
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait   = WebDriverWait(self.driver, 40)

    # ===================== RUN ===================== #

    def run(self):
        try:
            for category in self.CATEGORIES:
                self._scrape_category(category)
        finally:
            self.driver.quit()

        return self.results

    def _scrape_category(self, category: str):
        base_cat_url = (
            f"{self.DOMAIN}/searchproperties/Include-Inactive/Units/{category}/"
        )
        page = 1

        while True:
            url = base_cat_url if page == 1 else f"{base_cat_url}?paging=true&page={page}"
            self.driver.get(url)

            # Wait until at least one propertyInfo link is in the DOM
            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//a[contains(@href,'propertyInfo')]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)

            # ── Collect detail-page hrefs (dedup: image link + button both point to same URL) ──
            hrefs = tree.xpath("//a[contains(@href,'propertyInfo')]/@href")
            seen_page = set()
            unique = []
            for h in hrefs:
                if h not in seen_page:
                    seen_page.add(h)
                    unique.append(h)


            if not unique:
                break

            for href in unique:
                detail_url = urljoin(self.DOMAIN, href) if not href.startswith("http") else href

                if detail_url in self.seen_urls:
                    continue
                self.seen_urls.add(detail_url)

                try:
                    obj = self.parse_listing(detail_url)
                    if obj:
                        self.results.append(obj)
                except Exception:
                    pass

            # ── Next page? ──
            next_links = tree.xpath(
                f"//div[contains(@class,'divPaging')]"
                f"//a[contains(@href,'page={page + 1}')]"
            )
            if not next_links:
                break

            page += 1

    # ===================== DETAIL PAGE (requests — no Selenium) ===================== #

    def parse_listing(self, url: str):
        """
        Detail pages render fully as static HTML — no JS execution needed.
        Using requests is ~10× faster than Selenium for these pages.
        """
        try:
            resp = self.session.get(url, timeout=20)
            resp.raise_for_status()
        except Exception:
            return None

        tree = html.fromstring(resp.text)

        # ── ADDRESS (h2 heading that contains the full address) ──
        # The rendered page has a single large h2 with the address text
        address_h2 = tree.xpath(
            "//div[contains(@class,'obj50L') and not(contains(@class,'objR'))]"
            "//h2[contains(@class,'propTitle')]"
        )
        if address_h2:
            display_address = self._clean(
                " ".join(address_h2[0].itertext())
            )
        else:
            # Fallback: grab from <title>
            title = tree.xpath("//title/text()")
            display_address = self._clean(title[0]) if title else ""

        # ── RIGHT COLUMN: status / type / size ──
        right_h2s = tree.xpath(
            "//div[contains(@class,'objR') and contains(@class,'obj50L')]"
            "//h2[contains(@class,'propTitle')]"
        )
        status_raw        = self._clean("".join(right_h2s[0].itertext())) if len(right_h2s) > 0 else ""
        property_sub_type = self._clean("".join(right_h2s[1].itertext())) if len(right_h2s) > 1 else ""
        size_raw          = self._clean("".join(right_h2s[2].itertext())) if len(right_h2s) > 2 else ""

        sale_type        = self.normalize_sale_type(status_raw)
        size_ft, size_ac = self.extract_size(size_raw)

        # ── BULLET POINTS (description) ──
        bullets = tree.xpath(
            "//div[contains(@class,'alternList')]//li//text()"
        )
        detailed_description = self._clean(" | ".join(
            b.strip() for b in bullets if b.strip()
        ))

        # ── PRICE ──
        price = self.extract_numeric_price(detailed_description, sale_type)

        # ── TENURE ──
        tenure = self.extract_tenure(detailed_description)

        # ── POSTCODE ──
        postal_code = self.extract_postcode(display_address)

        # ── IMAGES ──
        # On the static render, images appear as plain <img> tags.
        # Full-size = _web.jpg, thumbnails = _sm.jpg — exclude thumbnails.
        all_imgs = tree.xpath("//img/@src")
        property_images = [
            src for src in all_imgs
            if "agencypilot.com/store/property" in src and "_sm." not in src
        ]

        # ── BROCHURE ──
        brochure_urls = tree.xpath("//a[contains(@id,'hypBrochure')]/@href")
        if not brochure_urls:
            brochure_urls = [
                href for href in tree.xpath("//a/@href")
                if ".pdf" in href.lower()
            ]

        # ── AGENT ──
        agent_name = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'contactPanel')]"
                "//h2//text()"
            )
        ))
        agent_email_hrefs = tree.xpath(
            "//div[contains(@class,'contactPanel')]"
            "//a[starts-with(@href,'mailto:')]/@href"
        )
        agent_email = (
            agent_email_hrefs[0].replace("mailto:", "").strip()
            if agent_email_hrefs else ""
        )

        obj = {
            "listingUrl":          url,
            "displayAddress":      display_address,
            "price":               price,
            "propertySubType":     property_sub_type,
            "propertyImage":       property_images,
            "detailedDescription": detailed_description,
            "sizeFt":              size_ft,
            "sizeAc":              size_ac,
            "postalCode":          postal_code,
            "brochureUrl":         brochure_urls,
            "agentCompanyName":    "NPS Property",
            "agentName":           agent_name,
            "agentCity":           "",
            "agentEmail":          agent_email,
            "agentPhone":          "",
            "agentStreet":         "",
            "agentPostcode":       "",
            "tenure":              tenure,
            "saleType":            sale_type,
        }

        return obj

    # ===================== HELPERS ===================== #

    def extract_size(self, text):
        if not text:
            return "", ""
        t = text.lower().replace(",", "")
        t = re.sub(r"[–—−]", "-", t)
        size_ft = ""
        size_ac = ""

        # sq ft
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(sq\.?\s*ft\.?|sqft|sf|square\s*f(?:eet|oot))', t)
        if m:
            a, b = float(m.group(1)), (float(m.group(2)) if m.group(2) else None)
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        # sq m → sq ft
        if not size_ft:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(sq\.?\s*m\.?|sqm|m2|square\s*metr)', t)
            if m:
                a, b = float(m.group(1)), (float(m.group(2)) if m.group(2) else None)
                size_ft = round((min(a, b) if b else a) * 10.7639, 3)

        # acres
        m = re.search(
            r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
            r'(acres?|acre|ac\.?)', t)
        if m:
            a, b = float(m.group(1)), (float(m.group(2)) if m.group(2) else None)
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        # hectares → acres
        if not size_ac:
            m = re.search(
                r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*'
                r'(hectares?|ha)', t)
            if m:
                a, b = float(m.group(1)), (float(m.group(2)) if m.group(2) else None)
                size_ac = round((min(a, b) if b else a) * 2.47105, 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale" or not text:
            return ""
        t = text.lower()
        if any(k in t for k in ["poa", "price on application", "upon application", "on application"]):
            return ""
        if any(k in t for k in ["per annum", " pa", "per year", "pcm", "per month", " pw", "per week", "rent"]):
            return ""
        m = re.search(r"(?:£|€|\$)\s*(\d+(?:,\d{3})*(?:\.\d+)?)(\s*[mk])?", t)
        if not m:
            return ""
        num = float(m.group(1).replace(",", ""))
        suffix = (m.group(2) or "").strip().lower()
        if suffix == "m": num *= 1_000_000
        elif suffix == "k": num *= 1_000
        return str(int(num))

    def extract_tenure(self, text):
        if not text:
            return ""
        t = text.lower()
        if "freehold" in t:  return "Freehold"
        if "leasehold" in t: return "Leasehold"
        if "fbt" in t or "farm business tenancy" in t: return "FBT"
        return ""

    def extract_postcode(self, text: str):
        if not text:
            return ""
        t = text.upper()
        m = re.search(r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b', t)
        if m: return m.group().strip()
        m = re.search(r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b', t)
        return m.group().strip() if m else ""

    def normalize_sale_type(self, text):
        t = text.lower()
        if "under offer" in t: return "Under Offer"
        if "for sale" in t or "sale" in t: return "For Sale"
        if "to let" in t or "let" in t or "rent" in t: return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""


# ===================== ENTRY POINT ===================== #

if __name__ == "__main__":
    import json

    scraper = NPSScraper()
    data = scraper.run()

    with open("nps_results.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)