import re
import json
import math
import time
import random

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


class CWMScraper:
    DOMAIN  = "https://www.cbre.co.uk"
    API_URL = "https://www.cbre.co.uk/property-api/propertylistings/query"

    # London bounding box
    LAT     = "51.5072178"
    LON     = "-0.12775829999998223"
    LON2    = "-0.1275862"
    POLYGON = '[["52.12183217126288,0.30120681171876384","51.04845176785064,0.30120681171876384","51.04845176785064,-0.7040422117187362","52.12183217126288,-0.7040422117187362"]]'

    SELECT_FIELDS = (
        "Dynamic.PrimaryImage,Common.ActualAddress,Common.Charges,"
        "Common.PrimaryKey,Common.UsageType,Common.Coordinate,Common.Aspects,"
        "Common.ListingCount,Common.IsParent,Common.HomeSite,Common.Agents,"
        "Common.PropertySubType,Common.PropertyTypes,Common.ContactGroup,"
        "Common.Highlights,Common.Walkthrough,Common.MinimumSize,Common.MaximumSize,"
        "Common.TotalSize,Common.GeoLocation,Common.Sizes,Common.LeaseTypes"
    )

    PAGE_SIZE = 24

    TYPE_MAP = {
        "office":     ("Office",     "office-space"),
        "retail":     ("Retail",     "retail-space"),
        "industrial": ("Industrial", "industrial-space"),
    }

    DEAL_MAP = {
        "rent": ("isLetting", "To Let"),
        "sale": ("isSale",    "For Sale"),
    }

    def __init__(self):
        self.results   = []
        self.seen_keys = set()

        opts = Options()
        opts.binary_location = "/usr/bin/chromium-browser"
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--window-size=1920,1080")
        opts.add_argument(
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        )
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        opts.add_argument("--disable-blink-features=AutomationControlled")

        svc =Service("/usr/bin/chromedriver")
        self.driver = webdriver.Chrome(service=svc, options=opts)
        self.driver.execute_cdp_cmd(
            "Page.addScriptToEvaluateOnNewDocument",
            {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"},
        )
        self.driver.set_script_timeout(60)   # allow up to 60s for async scripts
        self.wait = WebDriverWait(self.driver, 40)

        # Load the search page once so CF sets cookies on this browser session
        self._warm_up()

    # ──────────────────────────────────────────────────────────────────────
    # Warm-up: establish a trusted CF session
    # ──────────────────────────────────────────────────────────────────────

    def _warm_up(self):
        url = (
            f"{self.DOMAIN}/property-search/office-space"
            f"/listings/results?aspects=isLetting"
        )
        self.driver.get(url)
        try:
            self.wait.until(EC.presence_of_element_located(
                (By.XPATH, "//div[contains(@class,'r4PropertyCard')]")
            ))
        except TimeoutException:
            pass


    def _fetch_api(self, usage_type, aspect_flag, page, type_slug):
        from urllib.parse import urlencode

        params = {
            "Site":             "uk-comm",
            "Interval":         "Annually",
            "RadiusType":       "Miles",
            "CurrencyCode":     "GBP",
            "Unit":             "sqft",
            "lon":              self.LON2,
            "Lat":              self.LAT,
            "Lon":              self.LON,
            "PolygonFilters":   self.POLYGON,
            "Common.Aspects":   aspect_flag,
            "Sort":             "desc(Common.LastUpdated)",
            "Common.UsageType": usage_type,
            "PageSize":         str(self.PAGE_SIZE),
            "Page":             str(page),
            "_select":          self.SELECT_FIELDS,
        }
        url = f"{self.API_URL}?{urlencode(params)}"

        # Synchronous XHR — execute_script blocks until JS returns
        js = """
        var url = arguments[0];
        var xhr = new XMLHttpRequest();
        xhr.open('GET', url, false);          // false = synchronous
        xhr.setRequestHeader('Accept', 'application/json, text/javascript, */*; q=0.01');
        xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
        try {
            xhr.send(null);
            return xhr.responseText;
        } catch(e) {
            return 'ERROR:' + e.toString();
        }
        """

        try:
            raw = self.driver.execute_script(js, url)
        except Exception:
            return None

        if not raw:
            return None

        if isinstance(raw, str) and raw.startswith("ERROR:"):
            return None

        if not str(raw).strip().startswith("{"):
            return None

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None


    def _random_delay(self, lo=1.0, hi=2.5):
        time.sleep(random.uniform(lo, hi))

    def _clean(self, val):
        return " ".join(str(val).split()) if val else ""

    def normalize_sale_type(self, aspects):
        a = " ".join(aspects or []).lower()
        if "isletting" in a: return "To Let"
        if "issale"    in a: return "For Sale"
        return ""

    def extract_postcode(self, text):
        if not text: return ""
        t = text.upper()
        m = re.search(r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b', t)
        if m: return m.group().strip()
        m = re.search(r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b', t)
        return m.group().strip() if m else ""

    def extract_tenure(self, lease_types, description=""):
        combined = " ".join(lease_types or []).lower()
        if "freehold"  in combined: return "Freehold"
        if "leasehold" in combined or "sublease" in combined: return "Leasehold"
        d = (description or "").lower()
        if "freehold"  in d: return "Freehold"
        if "leasehold" in d: return "Leasehold"
        return ""

    def build_display_address(self, addr):
        if not isinstance(addr, dict): return ""
        parts = []
        for k in ("Common.Line1", "Common.Line2", "Common.Line3",
                  "Common.Locallity", "Common.Region"):
            v = (addr.get(k) or "").strip()
            if v and v not in parts:
                parts.append(v)
        return ", ".join(p for p in parts if p)

    def get_postcode(self, addr):
        if isinstance(addr, dict):
            pc = (addr.get("Common.PostCode") or "").strip()
            if pc: return pc
        return self.extract_postcode(self.build_display_address(addr))

    def build_description(self, listing):
        highlights = listing.get("Common.Highlights") or []
        texts = []
        for h in highlights:
            if not isinstance(h, dict): continue
            for item in (h.get("Common.Highlight") or []):
                if isinstance(item, dict):
                    t = self._clean(item.get("Common.Text", ""))
                    if t: texts.append(t)
        return " | ".join(texts)

    def extract_size(self, listing):
        size_ft = ""
        size_ac = ""

        total_list = listing.get("Common.TotalSize") or []
        for item in (total_list if isinstance(total_list, list) else [total_list]):
            if not isinstance(item, dict): continue
            unit = str(item.get("Common.Units", "")).lower()
            raw  = item.get("Common.Size")
            if raw:
                try:
                    v = float(raw)
                    if "acre" in unit:        size_ac = round(v, 3)
                    elif "sqm" in unit:       size_ft = round(v * 10.7639, 3)
                    else:                     size_ft = round(v, 3)
                    break
                except: pass

        if not size_ft and not size_ac:
            for s in (listing.get("Common.Sizes") or []):
                if not isinstance(s, dict): continue
                for d in (s.get("Common.Dimensions") or []):
                    unit = str(d.get("Common.DimensionsUnits", "")).lower()
                    raw  = d.get("Common.Amount")
                    if raw:
                        try:
                            v = float(raw)
                            if "acre" in unit:  size_ac = round(v, 3)
                            elif "sqm" in unit: size_ft = round(v * 10.7639, 3)
                            else:               size_ft = round(v, 3)
                        except: pass
                if size_ft or size_ac: break

        return size_ft, size_ac

    def extract_price(self, listing, sale_type):
        if sale_type != "For Sale": return ""
        for c in (listing.get("Common.Charges") or []):
            if not isinstance(c, dict): continue
            kind   = str(c.get("Common.ChargeKind", "")).lower()
            on_app = c.get("Common.OnApplication", False)
            if ("sale" in kind or "asking" in kind) and not on_app:
                raw = c.get("Common.Amount")
                if raw:
                    try: return str(int(float(raw)))
                    except: pass
        return ""

    def extract_images(self, listing):
        img_obj = listing.get("Dynamic.PrimaryImage")
        if not isinstance(img_obj, dict): return []
        resources = img_obj.get("Common.ImageResources") or []
        for bp in ("large", "medium", "small", "original"):
            for r in resources:
                if isinstance(r, dict) and r.get("Common.Breakpoint") == bp:
                    uri = r.get("Source.Uri") or r.get("Common.Resource.Uri", "")
                    if uri:
                        return [uri if uri.startswith("http") else f"{self.DOMAIN}{uri}"]
        return []

    def extract_agents(self, listing):
        """Return details for the first (primary) agent only."""
        agents = listing.get("Common.Agents") or []
        if not isinstance(agents, list):
            agents = [agents]
        for a in agents:
            if not isinstance(a, dict):
                continue
            name  = self._clean(a.get("Common.AgentName", ""))
            email = self._clean(a.get("Common.EmailAddress", ""))
            phone = self._clean(a.get("Common.TelephoneNumber", ""))
            if name or email or phone:
                return name, email, phone
        return "", "", ""

    def build_listing_url(self, listing, type_slug):
        key  = listing.get("Common.PrimaryKey", "")
        addr = listing.get("Common.ActualAddress") or {}
        parts = [
            (addr.get(k) or "").strip()
            for k in ("Common.Line1", "Common.Line2", "Common.Locallity", "Common.PostCode")
        ]
        slug = "-".join(p for p in parts if p)
        slug = re.sub(r"[^a-zA-Z0-9\s-]", "", slug)
        slug = re.sub(r"\s+", "-", slug).lower()
        slug = re.sub(r"-+", "-", slug).strip("-")
        return f"{self.DOMAIN}/property-search/{type_slug}/listings/details/{key}/{slug}"

    def _build_record(self, listing, sale_type_label, type_slug):
        addr            = listing.get("Common.ActualAddress") or {}
        display_address = self.build_display_address(addr)
        postcode        = self.get_postcode(addr)
        aspects         = listing.get("Common.Aspects") or []
        sale_type       = self.normalize_sale_type(aspects) or sale_type_label
        description     = self.build_description(listing)
        size_ft, size_ac = self.extract_size(listing)
        prop_sub = listing.get("Common.PropertySubType") or listing.get("Common.UsageType") or ""
        if isinstance(prop_sub, list): prop_sub = prop_sub[0] if prop_sub else ""
        agent_name, agent_email, agent_phone = self.extract_agents(listing)

        return {
            "listingUrl":          self.build_listing_url(listing, type_slug),
            "displayAddress":      display_address,
            "price":               self.extract_price(listing, sale_type),
            "propertySubType":     self._clean(str(prop_sub)),
            "propertyImage":       self.extract_images(listing),
            "detailedDescription": description,
            "sizeFt":              size_ft,
            "sizeAc":              size_ac,
            "postalCode":          self._clean(postcode),
            "brochureUrl":         [],
            "agentCompanyName":    "CBRE",
            "agentName":           agent_name,
            "agentCity":           "",
            "agentEmail":          agent_email,
            "agentPhone":          agent_phone,
            "agentStreet":         "",
            "agentPostcode":       "",
            "tenure":              self.extract_tenure(
                                       listing.get("Common.LeaseTypes"), description),
            "saleType":            sale_type,
        }


    def run(self):
        for prop_key, (usage_type, type_slug) in self.TYPE_MAP.items():
            for deal_key, (aspect_flag, sale_type_label) in self.DEAL_MAP.items():

                page       = 1
                total_hit  = 0
                total_docs = None

                while True:
                    data = self._fetch_api(usage_type, aspect_flag, page, type_slug)

                    if data is None:
                        break

                    if not data.get("Found", False):
                        break

                    if total_docs is None:
                        total_docs  = int(data.get("DocumentCount", 0))

                    outer = data.get("Documents") or []
                    listings = outer[0] if outer and isinstance(outer[0], list) else []

                    if not listings:
                        break

                    for listing in listings:
                        key = listing.get("Common.PrimaryKey", "")
                        if key in self.seen_keys:
                            continue
                        self.seen_keys.add(key)
                        try:
                            record = self._build_record(listing, sale_type_label, type_slug)
                            self.results.append(record)
                            total_hit += 1
    
                        except Exception:
                            pass

                    fetched = (page - 1) * self.PAGE_SIZE + len(listings)
                    if fetched >= total_docs or len(listings) < self.PAGE_SIZE:
                        break

                    page += 1
                    self._random_delay(0.8, 2.0)

        self.driver.quit()
        return self.results