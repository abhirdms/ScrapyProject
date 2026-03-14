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


# ══════════════════════════════════════════════════════════════
#  SHARED CHROME FACTORY
# ══════════════════════════════════════════════════════════════

def _make_driver():
    chrome_options = Options()
    # chrome_options.binary_location = "/usr/bin/chromium-browser"   # Linux
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    # service = Service("/usr/bin/chromedriver")                       # Linux
    service = Service(
        "C:/Users/educa/Downloads/ScrapyProject/ScrapyProject/chromedriver.exe"
    )
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver, WebDriverWait(driver, 25)


# ══════════════════════════════════════════════════════════════
#  SHARED HELPERS
# ══════════════════════════════════════════════════════════════

class _Helpers:

    # ---- SIZE ---- #
    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = text.replace("ft²", " sq ft ").replace("m²", " sqm ")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = size_ac = ""

        # square feet
        m = re.search(
            r"(\d[\d\.]*)\s*(?:-|to)?\s*(\d[\d\.]*)?\s*"
            r"(sq\.?\s*ft\.?|sqft|square\s*feet|square\s*foot|sq\s*feet)\b",
            text)
        if m:
            a, b = float(m.group(1)), float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        # square metres → sqft
        if not size_ft:
            m = re.search(
                r"(\d[\d\.]*)\s*(?:-|to)?\s*(\d[\d\.]*)?\s*"
                r"(sqm|sq\.?\s*m\b|m2\b|square\s*metres|square\s*meters)\b",
                text)
            if m:
                a, b = float(m.group(1)), float(m.group(2)) if m.group(2) else None
                size_ft = round((min(a, b) if b else a) * 10.7639, 3)

        # acres — requires word boundary, NOT matching "spaces", "place", etc.
        m = re.search(
            r"(\d[\d\.]*)\s*(?:-|to)?\s*(\d[\d\.]*)?\s*\b(acres?|ac)\b",
            text)
        if m:
            a, b = float(m.group(1)), float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        # hectares → acres
        if not size_ac:
            m = re.search(
                r"(\d[\d\.]*)\s*(?:-|to)?\s*(\d[\d\.]*)?\s*\b(hectares?|ha)\b",
                text)
            if m:
                a, b = float(m.group(1)), float(m.group(2)) if m.group(2) else None
                size_ac = round((min(a, b) if b else a) * 2.47105, 3)

        return size_ft, size_ac

    # ---- PRICE ---- #
    def extract_any_price(self, text):
        if not text:
            return ""
        t = text.lower()
        if any(k in t for k in ["poa", "price on application", "upon application",
                                  "contact us for price", "please contact", "call for"]):
            return ""
        m = re.search(r"(?:£|€|\$)\s*([\d,]+(?:\.\d+)?)(\s*[mk])?", t)
        if not m:
            return ""
        num = float(m.group(1).replace(",", ""))
        suffix = (m.group(2) or "").strip().lower()
        if suffix == "m":
            num *= 1_000_000
        elif suffix == "k":
            num *= 1_000
        return str(int(num))

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale":
            return ""
        t = (text or "").lower()
        if any(k in t for k in ["per annum", " pa ", "per year", "pcm",
                                  "per month", " pw ", "per week", "rent"]):
            return ""
        return self.extract_any_price(text)

    # ---- TENURE ---- #
    def extract_tenure(self, text):
        t = (text or "").lower()
        if "freehold" in t:
            return "Freehold"
        if "leasehold" in t:
            return "Leasehold"
        return ""

    # ---- POSTCODE ---- #
    def extract_postcode(self, text):
        if not text:
            return ""
        text = text.upper()
        m = re.search(r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b", text)
        if m:
            return m.group().strip()
        m = re.search(r"\b[A-Z]{1,2}\d{1,2}[A-Z]?\b", text)
        return m.group().strip() if m else ""

    def extract_postcode_from_url(self, url):
        """Extracts postcode from property.jll.co.uk URL slug e.g. …-e1w-2da-290503"""
        m = re.search(
            r"/(?:rent-office|sale-office|listings)/[^/]*?"
            r"-([a-z]{1,2}\d{1,2}[a-z]?)-(\d[a-z]{2})-\d+$",
            url, re.IGNORECASE)
        if m:
            return f"{m.group(1).upper()} {m.group(2).upper()}"
        return ""

    # ---- SALE TYPE ---- #
    def normalize_sale_type(self, text):
        t = (text or "").lower()
        if "for sale" in t or "to buy" in t:
            return "For Sale"
        if "for rent" in t or "to let" in t or "to rent" in t:
            return "To Let"
        return ""

    # ---- PROPERTY SUB TYPE ---- #
    def normalize_property_sub_type(self, text):
        t = (text or "").lower()
        if "flex" in t:
            return "Flex Office"
        if "office" in t:
            return "Office"
        if "industrial" in t or "warehouse" in t or "logistics" in t:
            return "Industrial / Warehouse"
        if "retail" in t:
            return "Retail"
        if "hotel" in t or "hospitality" in t:
            return "Hotels & Hospitality"
        if "multifamily" in t or "apartment" in t or "flat" in t:
            return "Residential"
        if "land" in t:
            return "Land"
        return self._clean(text)

    # ---- UTILITY ---- #
    def _clean(self, val):
        return " ".join(val.split()) if val else ""

    def _empty_obj(self, url):
        return {
            "listingUrl": url,
            "displayAddress": "",
            "price": "",
            "propertySubType": "",
            "propertyImage": [],
            "detailedDescription": "",
            "sizeFt": "",
            "sizeAc": "",
            "postalCode": "",
            "brochureUrl": [],
            "agentCompanyName": "JLL",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": "",
            "saleType": "",
        }

    # ---- SECTION TEXT (targeted, no full-page spill) ---- #
    def _section_text(self, tree, *heading_names):
        """
        Pull text ONLY from the content block that follows a given heading.
        Tries multiple heading names for resilience.
        """
        for name in heading_names:
            # h2 / h3 immediately followed by sibling div or ul/li
            texts = tree.xpath(
                f"//h2[normalize-space()='{name}']"
                "/following-sibling::*[self::p or self::ul or self::div][1]//text() | "
                f"//h3[normalize-space()='{name}']"
                "/following-sibling::*[self::p or self::ul or self::div][1]//text()"
            )
            # broader ancestor approach
            if not texts:
                texts = tree.xpath(
                    f"//section[.//*[normalize-space()='{name}']]"
                    "//*[self::p or self::li][not(ancestor::nav)]//text()"
                )
            result = self._clean(" ".join(texts))
            if result:
                return result
        return ""

    def _agent_names(self, tree):
        """
        Robust agent name extraction for JLL pages.
        JLL renders agents as: <img alt="Agent Name"> inside an agent card,
        OR as plain text in a heading near an 'Agent details' link.
        """
        # Method 1 — img alt inside agent/broker section (most reliable on JLL)
        names = tree.xpath(
            "//section[contains(translate(.,'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
            "'abcdefghijklmnopqrstuvwxyz'),'agent')]"
            "//img/@alt"
        )
        names = [self._clean(n) for n in names
                 if n and len(n.strip()) > 2
                 and n.strip().lower() not in ("", "agent", "broker")]
        if names:
            return names

        # Method 2 — heading right before "Agent details" link
        names = tree.xpath(
            "//a[contains(normalize-space(.),'Agent details') or "
            "    contains(normalize-space(.),'agent details')]"
            "/preceding::*[self::h2 or self::h3 or self::p][1]/text()"
        )
        names = [self._clean(n) for n in names if n and len(n.strip()) > 2]
        if names:
            return names

        # Method 3 — Cloudinary broker profile image alt
        names = tree.xpath(
            "//img[contains(@src,'broker_profile') or "
            "      contains(@src,'jll-global-broker-profile')]/@alt"
        )
        return [self._clean(n) for n in names
                if n and len(n.strip()) > 2
                and n.strip().lower() not in ("", "agent", "broker")]


# ══════════════════════════════════════════════════════════════
#  SCRAPER 1 — property.jll.co.uk  (commercial office / rent)
# ══════════════════════════════════════════════════════════════

class JLLCommercialScraper(_Helpers):
    BASE_URL    = "https://property.jll.co.uk/search"
    DOMAIN      = "https://property.jll.co.uk"
    SEARCH_PARAMS = (
        "?tenureTypes=rent&propertyTypes=office"
        "&orderBy=desc&sortBy=dateModifiedAtSource"
    )

    def __init__(self):
        self.results   = []
        self.seen_urls = set()
        self.driver, self.wait = _make_driver()

    def run(self):
        page = 1
        while True:
            url = (
                f"{self.BASE_URL}{self.SEARCH_PARAMS}"
                if page == 1
                else f"{self.BASE_URL}{self.SEARCH_PARAMS}&page={page}"
            )
            self.driver.get(url)
            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//a[contains(@href,'/rent-office/') or contains(@href,'/listings/')]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)
            hrefs = list(dict.fromkeys(tree.xpath(
                "//a[contains(@href,'/rent-office/') or contains(@href,'/listings/')]/@href"
            )))
            if not hrefs:
                break

            new_found = False
            for href in hrefs:
                full_url = urljoin(self.DOMAIN, href)
                if full_url in self.seen_urls:
                    continue
                self.seen_urls.add(full_url)
                new_found = True
                try:
                    obj = self._parse_listing(full_url)
                    if obj:
                        self.results.append(obj)
                        if len(self.results)>10:
                            return self.results
                        
                except Exception:
                    pass

            if not new_found:
                break
            page += 1

        self.driver.quit()
        return self.results

    def _parse_listing(self, url):
        self.driver.get(url)
        self.wait.until(EC.presence_of_element_located((By.XPATH, "//h1")))
        tree = html.fromstring(self.driver.page_source)

        # --- address ---
        building_name = self._clean(" ".join(tree.xpath("//h1/text()")))

        # street line is normally a <p> or sibling element right after h1
        street = self._clean(" ".join(tree.xpath(
            "//h1/following-sibling::p[1]/text() | "
            "//h1/following-sibling::span[1]/text()"
        )))

        # breadcrumbs: CITY / POSTCODE links
        bc_items = [
            self._clean(t) for t in tree.xpath(
                "//a[contains(@href,'city=') or contains(@href,'postcode=')]/text()"
            )
        ]
        _skip = {"office", "north west", "greater manchester",
                 "manchester city centre", "south east", "london"}
        address_parts = [p for p in [building_name, street] + bc_items
                         if p and p.lower() not in _skip]
        display_address = ", ".join(dict.fromkeys(address_parts))

        # --- size: take ONLY from visible hero/stats area, not full page ---
        # JLL shows "14,770 ft² / 1,372 m²" in a dedicated stats block
        size_raw = self._clean(" ".join(tree.xpath(
            "//li[contains(.,'ft²') or contains(.,'sq ft')]//text() | "
            "//*[contains(@class,'stat') or contains(@class,'Stat') or "
            "    contains(@class,'space') or contains(@class,'Space')]"
            "[contains(.,'ft²') or contains(.,'sq ft') or contains(.,'m²')]//text()"
        )))
        # Fallback: scan first 500 chars of page (hero area)
        if not size_raw:
            page_text = self.driver.execute_script(
                "return document.body.innerText.slice(0, 800);"
            )
            size_raw = page_text or ""

        size_ft, size_ac = self.extract_size(size_raw)

        # --- description: ONLY named sections, never full page ---
        summary       = self._section_text(tree, "Summary")
        description   = self._section_text(tree, "Description")
        specification = self._section_text(tree, "Specification")
        accommodation = self._section_text(tree, "Accommodation")
        location      = self._section_text(tree, "Location")

        detailed_description = " ".join(
            p for p in [summary, description, specification, accommodation, location]
            if p
        )

        # --- price / tenure / sale type ---
        title_text = self._clean(" ".join(tree.xpath("//title/text()")))
        sale_type  = self.normalize_sale_type(title_text) or "To Let"
        tenure     = self.extract_tenure(detailed_description)

        # Price label shown near hero (e.g. "£25 per ft²")
        price_raw = self._clean(" ".join(tree.xpath(
            "//*[contains(@class,'price') or contains(@class,'Price')]//text()"
        )))
        price = self.extract_numeric_price(price_raw + " " + detailed_description, sale_type)

        # --- property sub type ---
        property_sub_type = self.normalize_property_sub_type(title_text)

        # --- images (exclude agent portraits) ---
        property_images = list(dict.fromkeys(
            src for src in tree.xpath("//img[contains(@src,'res.cloudinary.com')]/@src")
            if src and not any(x in src for x in [
                "broker_profile", "jll-global-broker-profile", "flag-", "logo"
            ])
        ))

        # --- brochures ---
        brochure_urls = list(dict.fromkeys(
            href if href.startswith("http") else urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
        ))

        # --- agents ---
        names = self._agent_names(tree)
        agent_name = names[0] if names else ""

        postcode = self.extract_postcode_from_url(url) or self.extract_postcode(display_address)

        obj = self._empty_obj(url)
        obj.update({
            "displayAddress":      display_address,
            "price":               price,
            "propertySubType":     property_sub_type,
            "propertyImage":       property_images,
            "detailedDescription": detailed_description,
            "sizeFt":              size_ft,
            "sizeAc":              size_ac,
            "postalCode":          postcode,
            "brochureUrl":         brochure_urls,
            "agentName":           agent_name,
            "tenure":              tenure,
            "saleType":            sale_type,
        })
        return obj


# ══════════════════════════════════════════════════════════════
#  SCRAPER 2 — invest.jll.com  (investment / for sale)
# ══════════════════════════════════════════════════════════════

class JLLInvestScraper(_Helpers):
    """
    invest.jll.com is a heavy React SPA.
    - Search page uses infinite scroll (no ?page= param)
    - Listing cards render as <a href="/uk/en/listing/...">
    - Individual listing pages also require JS rendering
    """
    SEARCH_URL = "https://invest.jll.com/uk/en/property-search"
    DOMAIN     = "https://invest.jll.com"

    def __init__(self):
        self.results   = []
        self.seen_urls = set()
        self.driver, self.wait = _make_driver()

    def run(self):
        self.driver.get(self.SEARCH_URL)

        # Wait for at least one listing card link
        try:
            self.wait.until(EC.presence_of_element_located((
                By.XPATH, "//a[contains(@href,'/listing/')]"
            )))
        except Exception:
            self.driver.quit()
            return self.results

        # Infinite scroll: keep scrolling until no new cards appear for 3 rounds
        stable_rounds = 0
        last_count    = 0
        while stable_rounds < 3:
            self.driver.execute_script(
                "window.scrollTo(0, document.body.scrollHeight);"
            )
            time.sleep(2.5)
            tree  = html.fromstring(self.driver.page_source)
            hrefs = tree.xpath("//a[contains(@href,'/listing/')]/@href")
            count = len(set(hrefs))
            if count == last_count:
                stable_rounds += 1
            else:
                stable_rounds = 0
            last_count = count

        # Collect final set of listing URLs
        tree = html.fromstring(self.driver.page_source)
        listing_urls = list(dict.fromkeys(
            urljoin(self.DOMAIN, h)
            for h in tree.xpath("//a[contains(@href,'/listing/')]/@href")
        ))

        for url in listing_urls:
            if url in self.seen_urls:
                continue
            self.seen_urls.add(url)
            try:
                obj = self._parse_listing(url)
                if obj:
                    self.results.append(obj)
                    if len(self.results)>10:
                            return self.results
            except Exception:
                pass
        self.driver.quit()
        return self.results

    def _parse_listing(self, url):
        self.driver.get(url)

        # invest.jll.com is a full React app — wait for meaningful content
        try:
            self.wait.until(EC.presence_of_element_located((
                By.XPATH,
                "//h1 | //h2 | //*[contains(@class,'title') or contains(@class,'Title')]"
            )))
        except Exception:
            pass
        time.sleep(1.5)  # allow React to finish rendering

        tree = html.fromstring(self.driver.page_source)

        # --- address ---
        property_name = self._clean(" ".join(tree.xpath("//h1/text()")))
        # Sub-address: often in a <p> or span after h1
        address_parts_raw = tree.xpath(
            "//h1/following-sibling::p[1]//text() | "
            "//h1/following-sibling::span[1]//text() | "
            "//*[contains(@class,'subtitle') or contains(@class,'subTitle') or "
            "    contains(@class,'address')]//text()"
        )
        address_line  = self._clean(" ".join(address_parts_raw))
        display_address = ", ".join(p for p in [property_name, address_line] if p)

        # --- size ---
        # invest.jll cards show "19,589 sf" or "26 units" or "78.97 acres"
        size_raw = self._clean(" ".join(tree.xpath(
            "//*[contains(text(),' sf') or contains(text(),' sq ft') or "
            "    contains(text(),'ft²') or contains(text(),' acres') or "
            "    contains(text(),' units') or contains(text(),' m²')]//text() | "
            "//*[contains(@class,'size') or contains(@class,'area') or "
            "    contains(@class,'space')]//text()"
        )))
        size_ft, size_ac = self.extract_size(size_raw)

        # --- price ---
        price_raw = self._clean(" ".join(tree.xpath(
            "//*[contains(@class,'price') or contains(@class,'Price')]//text() | "
            "//span[contains(text(),'£') or contains(text(),'$') or "
            "       contains(text(),'€')]//text()"
        )))
        sale_type = "For Sale"  # invest.jll is always investment / for sale
        price = self.extract_any_price(price_raw)

        # --- property sub type ---
        asset_type_raw = self._clean(" ".join(tree.xpath(
            "//*[contains(@class,'assetType') or contains(@class,'asset-type') or "
            "    contains(@class,'propertyType') or contains(@class,'chip') or "
            "    contains(@class,'tag') or contains(@class,'badge')]//text()"
        )))
        property_sub_type = self.normalize_property_sub_type(asset_type_raw)

        # --- description: named sections only ---
        overview     = self._section_text(tree, "Overview", "Summary")
        highlights   = self._section_text(tree, "Highlights", "Key highlights")
        description  = self._section_text(tree, "Description", "Property description")
        location_txt = self._section_text(tree, "Location", "Location details")
        detailed_description = " ".join(
            p for p in [highlights, overview, description, location_txt] if p
        )
        tenure = self.extract_tenure(detailed_description)

        # --- images ---
        property_images = list(dict.fromkeys(
            src for src in tree.xpath("//img/@src | //img/@data-src")
            if src and "cloudinary" in src
            and not any(x in src for x in [
                "broker_profile", "flag-", "logo", "avatar", "profile"
            ])
        ))

        # --- brochures ---
        brochure_urls = list(dict.fromkeys(
            href if href.startswith("http") else urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
        ))

        # --- agents ---
        names = self._agent_names(tree)
        agent_name = names[0] if names else ""

        # Phone numbers shown on listing page
        phones = tree.xpath("//a[contains(@href,'tel:')]/@href")
        agent_phone = phones[0].replace("tel:", "").strip() if phones else ""

        postcode = self.extract_postcode(display_address)

        obj = self._empty_obj(url)
        obj.update({
            "displayAddress":      display_address,
            "price":               price,
            "propertySubType":     property_sub_type,
            "propertyImage":       property_images,
            "detailedDescription": detailed_description,
            "sizeFt":              size_ft,
            "sizeAc":              size_ac,
            "postalCode":          postcode,
            "brochureUrl":         brochure_urls,
            "agentName":           agent_name,
            "agentPhone":          agent_phone,
            "tenure":              tenure,
            "saleType":            sale_type,
        })

        return obj


# ══════════════════════════════════════════════════════════════
#  SCRAPER 3 — residential.jll.co.uk  (residential sale)
# ══════════════════════════════════════════════════════════════

class JLLResidentialScraper(_Helpers):
    BASE_URL    = "https://residential.jll.co.uk/search"
    DOMAIN      = "https://residential.jll.co.uk"
    SEARCH_PARAMS = "?tenureType=sale&currencyType=GBP&sortBy=price&sortDirection=desc"

    # Listing URL path prefixes recognised as property pages
    LISTING_PREFIXES = (
        "/sale-apartment/", "/sale-flat/", "/sale-house/",
        "/sale-development/", "/sale-penthouse/", "/sale-studio/",
        "/rent-apartment/", "/rent-flat/", "/rent-house/",
    )

    def __init__(self):
        self.results   = []
        self.seen_urls = set()
        self.driver, self.wait = _make_driver()

    def run(self):
        page = 1
        while True:
            url = (
                f"{self.BASE_URL}{self.SEARCH_PARAMS}"
                if page == 1
                else f"{self.BASE_URL}{self.SEARCH_PARAMS}&page={page}"
            )
            self.driver.get(url)

            # Build XPath condition from all prefixes
            cond = " or ".join(
                f"contains(@href,'{p}')" for p in self.LISTING_PREFIXES
            )
            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH, f"//a[{cond}]"
                )))
            except Exception:
                break

            tree = html.fromstring(self.driver.page_source)
            hrefs = list(dict.fromkeys(tree.xpath(f"//a[{cond}]/@href")))

            if not hrefs:
                break

            new_found = False
            for href in hrefs:
                if not href or href.startswith("#"):
                    continue
                full_url = urljoin(self.DOMAIN, href)
                if full_url in self.seen_urls:
                    continue
                self.seen_urls.add(full_url)
                new_found = True
                try:
                    obj = self._parse_listing(full_url)
                    if obj:
                        self.results.append(obj)
                        if len(self.results)>10:
                            return self.results
                except Exception:
                    pass

            if not new_found:
                break
            page += 1

        self.driver.quit()
        return self.results

    def _parse_listing(self, url):
        self.driver.get(url)

        # Resilient wait: accept h1 OR the price element OR the description block
        try:
            self.wait.until(EC.presence_of_element_located((
                By.XPATH,
                "//h1 | "
                "//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
                "'abcdefghijklmnopqrstuvwxyz'),'guide price') or "
                "    contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
                "'abcdefghijklmnopqrstuvwxyz'),'prices from')]"
            )))
        except Exception:
            # Page may still be partially loaded — give it a moment
            time.sleep(3)

        tree = html.fromstring(self.driver.page_source)

        # --- address ---
        property_name = self._clean(" ".join(tree.xpath("//h1/text()")))
        sub_address   = self._clean(" ".join(tree.xpath(
            "//h1/following-sibling::p[1]/text() | "
            "//h1/following-sibling::span[1]/text()"
        )))
        display_address = ", ".join(p for p in [property_name, sub_address] if p)

        # --- price ---
        # JLL residential shows "GUIDE PRICE £492,500" or "PRICES FROM £495,000"
        price_block = self._clean(" ".join(tree.xpath(
            "//*[contains(translate(text(),"
            "'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'GUIDE PRICE') or "
            "    contains(translate(text(),"
            "'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'PRICES FROM')]"
            "/following-sibling::*[1]//text() | "
            "//*[contains(translate(text(),"
            "'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'GUIDE PRICE') or "
            "    contains(translate(text(),"
            "'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'PRICES FROM')]"
            "/following::text()[1]"
        )))

        # --- sale type from URL path ---
        if any(p in url for p in ("/sale-", "/buy-")):
            sale_type = "For Sale"
        elif any(p in url for p in ("/rent-", "/let-")):
            sale_type = "To Let"
        else:
            title_text = self._clean(" ".join(tree.xpath("//title/text()")))
            sale_type  = self.normalize_sale_type(title_text) or "For Sale"

        price = self.extract_any_price(price_block) if sale_type == "For Sale" else ""

        # --- property sub type ---
        title_text        = self._clean(" ".join(tree.xpath("//title/text()")))
        property_sub_type = self._residential_sub_type(url, title_text)

        # --- description: targeted sections only ---
        highlights   = self._section_text(tree, "Highlights")
        description  = self._section_text(tree, "Description")
        location_txt = self._section_text(tree, "Location")

        detailed_description = " ".join(
            p for p in [highlights, description, location_txt] if p
        )

        # --- size: from description (residential rarely has structured size block) ---
        size_raw = self._clean(" ".join(tree.xpath(
            "//*[contains(text(),'sq ft') or contains(text(),'sqft') or "
            "    contains(text(),'ft²') or contains(text(),'square feet')]//text()"
        )))
        size_ft, size_ac = self.extract_size(size_raw or detailed_description)

        # --- tenure: from highlights / description ---
        tenure_extra = self._clean(" ".join(tree.xpath(
            "//*[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ',"
            "'abcdefghijklmnopqrstuvwxyz'),'tenure')]"
            "/following-sibling::*[1]//text()"
        )))
        tenure = self.extract_tenure(detailed_description + " " + tenure_extra)

        # --- images (exclude portraits, logos, flags) ---
        property_images = list(dict.fromkeys(
            src for src in tree.xpath(
                "//img[contains(@src,'res.cloudinary.com')]/@src | "
                "//img[contains(@data-src,'res.cloudinary.com')]/@data-src"
            )
            if src and not any(x in src for x in [
                "c_thumb,g_face", "grayscale", "flag-", "logo",
                "broker_profile", "jll-global-broker-profile"
            ])
        ))

        # --- brochures ---
        brochure_urls = list(dict.fromkeys(
            href if href.startswith("http") else urljoin(self.DOMAIN, href)
            for href in tree.xpath("//a[contains(@href,'.pdf')]/@href")
        ))

        # --- agents ---
        names = self._agent_names(tree)
        # JLL residential also embeds agent name in img alt of c_thumb portraits
        if not names:
            names = [
                self._clean(a) for a in tree.xpath(
                    "//img[contains(@src,'c_thumb') or contains(@src,'g_face')]/@alt"
                )
                if a and len(a.strip()) > 2
            ]
        agent_name = names[0] if names else ""

        phones = tree.xpath("//a[contains(@href,'tel:')]/@href")
        agent_phone = phones[0].replace("tel:", "").strip() if phones else ""

        # Agent city from "JLL - Greenwich" pattern near tel link
        city_labels = tree.xpath(
            "//a[contains(@href,'tel:')]"
            "/preceding::*[contains(text(),'JLL')][1]/text()"
        )
        city_raw   = city_labels[0] if city_labels else ""
        agent_city = self._clean(city_raw.split("-")[-1]) if "-" in city_raw else ""

        postcode = self.extract_postcode(display_address + " " + sub_address)

        obj = self._empty_obj(url)
        obj.update({
            "displayAddress":      display_address,
            "price":               price,
            "propertySubType":     property_sub_type,
            "propertyImage":       property_images,
            "detailedDescription": detailed_description,
            "sizeFt":              size_ft,
            "sizeAc":              size_ac,
            "postalCode":          postcode,
            "brochureUrl":         brochure_urls,
            "agentName":           agent_name,
            "agentPhone":          agent_phone,
            "agentCity":           agent_city,
            "tenure":              tenure,
            "saleType":            sale_type,
        })
        return obj

    def _residential_sub_type(self, url, title):
        u, t = url.lower(), title.lower()
        for keyword, label in [
            ("apartment", "Apartment"), ("flat",       "Flat"),
            ("penthouse", "Penthouse"), ("studio",     "Studio"),
            ("house",     "House"),     ("development","New Development"),
        ]:
            if keyword in u or keyword in t:
                return label
        return "Residential"


# ══════════════════════════════════════════════════════════════
#  COMBINED RUNNER
# ══════════════════════════════════════════════════════════════

class JLLScraper:
    """Run all three JLL scrapers sequentially; return one combined list."""

    def run(self):
        all_results = []

        for label, ScraperClass in [
            ("property.jll.co.uk  (Commercial / Office / Rent)", JLLCommercialScraper),
            ("invest.jll.com       (Investment / For Sale)",      JLLInvestScraper),
            ("residential.jll.co.uk (Residential / Sale)",        JLLResidentialScraper),
        ]:
            try:
                scraper = ScraperClass()
                results = scraper.run()
                all_results.extend(results)
            except Exception:
                pass

        return all_results


# ══════════════════════════════════════════════════════════════
#  ENTRY POINT
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    scraper = JLLAllScraper()
    data = scraper.run()