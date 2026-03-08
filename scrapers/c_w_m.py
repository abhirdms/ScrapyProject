import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class CWMScraper:
    DOMAIN = "https://www.cbre.co.uk"

    TYPE_MAP = {
        "office": "office-space",
        "retail": "retail-space",
        "industrial": "industrial-space"
    }

    DEAL_MAP = {
        "rent": "isLetting",
        "sale": "isSale"
    }

    def __init__(self):
        self.results = []
        self.seen_urls = set()

        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        service = Service("C:/Users/educa/Downloads/ScrapyProject/ScrapyProject/chromedriver.exe")
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 20)

    # ===================== RUN ===================== #

    def run(self):
        for prop_type in self.TYPE_MAP:
            for deal in self.DEAL_MAP:
                url = (
                    f"{self.DOMAIN}/property-search/"
                    f"{self.TYPE_MAP[prop_type]}/listings/results"
                    f"?aspects={self.DEAL_MAP[deal]}"
                )
                self.scrape_listing_pages(url, prop_type)

        self.driver.quit()
        return self.results

    def scrape_listing_pages(self, start_url, prop_type):
        self.driver.get(start_url)

        while True:
            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH, "//div[contains(@class,'r4PropertyCard')]"
                )))
            except:
                break

            tree = html.fromstring(self.driver.page_source)

            listing_urls = tree.xpath(
                "//div[contains(@class,'r4PropertyCard')]"
                "//a[contains(@href,'/property-search/')]/@href"
            )

            for href in listing_urls:
                url = urljoin(self.DOMAIN, href.split("?")[0])
                if url in self.seen_urls:
                    continue
                self.seen_urls.add(url)

                try:
                    objs = self.parse_listing(url, prop_type)
                    if objs:
                        if isinstance(objs, list):
                            self.results.extend(objs)
                        else:
                            self.results.append(objs)
                except:
                    continue

            try:
                next_btn = self.driver.find_element(
                    By.XPATH,
                    "//li[contains(@class,'next') and not(contains(@class,'disabled'))]//a"
                )
                self.driver.execute_script("arguments[0].click();", next_btn)
                self.wait.until(EC.staleness_of(
                    self.driver.find_elements(By.XPATH, "//div[contains(@class,'r4PropertyCard')]")[0]
                ))
            except:
                break

    # ===================== LISTING ===================== #

    def parse_listing(self, url, prop_type):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH, "//div[@data-test='address-line-1-']"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------- CLEAN DOM ---------- #
        for bad in tree.xpath(
            "//div[contains(@class,'subnav') "
            "or contains(@class,'graySubnav') "
            "or contains(@class,'sc-dWZqqJ')]"
        ):
            p = bad.getparent()
            if p is not None:
                p.remove(bad)

        # ---------- ADDRESS ---------- #
        addr1 = self._clean(" ".join(
            tree.xpath("//div[@data-test='address-line-1-']//span[last()]/text()")
        ))
        addr2 = self._clean(" ".join(
            tree.xpath("//div[@data-test='address-line-2-']//span/text()")
        ))
        display_address = f"{addr1} {addr2}".strip()

        # ---------- SALE TYPE ---------- #
        strap = self._clean(" ".join(
            tree.xpath("//span[@data-test='pdp-property-details-strapline']/text()")
        ))
        sale_type = self.normalize_sale_type(strap)

        # ---------- PRICE ---------- #
        price_text = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'headerValue')]//span/text()")
        ))
        price = self.extract_price_number(price_text, sale_type)

        # ---------- SIZE RANGE ---------- #
        size_range = self._clean(" ".join(
            tree.xpath("//h4[.='Size']/following-sibling::span//span/text()")
        ))
        min_sqft, max_sqft = self.extract_size_range(size_range)

        # ---------- DESCRIPTION ---------- #
        description = self._clean(" ".join(
            tree.xpath("//span[@data-test='pdp-property-long-description']/text()")
        ))

        specs = [
            self._clean(t) for t in
            tree.xpath("//ul[contains(@class,'cbre_bulletList')]//li/text()")
        ]
        if specs:
            description += " | " + " | ".join(specs)

        # ---------- RATES ---------- #
        business_rates = self.extract_rate(
            self._clean(" ".join(
                tree.xpath("//h3[.='Business Rates']/following-sibling::span/span/text()")
            ))
        )
        service_charge = self.extract_rate(
            self._clean(" ".join(
                tree.xpath("//h3[.='Service Charge']/following-sibling::span/span/text()")
            ))
        )

        # ---------- IMAGES ---------- #
        raw_imgs = tree.xpath(
            "//div[contains(@class,'cbre_imageCarousel')]//img[contains(@src,'_large')]/@src"
        )
        raw_imgs = list(dict.fromkeys(raw_imgs))
        images = [urljoin(self.DOMAIN, s.split("?")[0]) for s in raw_imgs]

        # ---------- BROCHURES ---------- #
        brochures = [
            urljoin(self.DOMAIN, h)
            for h in tree.xpath("//a[contains(@href,'.pdf')]/@href")
        ]

        # ---------- AGENTS ---------- #
        agents = [
            self._clean(t) for t in
            tree.xpath("//div[contains(@class,'singleContact')]//div[contains(@class,'bUEAgF')]/text()")
        ]

        postcode = self.extract_postcode(display_address)

        # ---------- FLOORS ---------- #
        floors = []
        rows = tree.xpath(
            "//div[contains(@class,'floorBlock')]//div[contains(@class,'cbre_table__row')]"
        )

        for r in rows:
            fname = self._clean(" ".join(r.xpath(".//h3/text()")))
            fsize = self._clean(" ".join(r.xpath(".//h4[.='Size']/following-sibling::span/text()")))
            fstatus = self._clean(" ".join(r.xpath(".//h4[.='Status']/following-sibling::text()")))

            fmin, fmax = self.extract_size_range(fsize)

            floors.append({
                "floor": fname,
                "sizeText": fsize,
                "minSqft": fmin,
                "maxSqft": fmax,
                "status": fstatus
            })

        # ---------- BASE OBJECT ---------- #
        base = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": prop_type.title(),
            "propertyImage": images,
            "detailedDescription": description.strip(),
            "sizeFtMin": min_sqft,
            "sizeFtMax": max_sqft,
            "postalCode": postcode,
            "brochureUrl": brochures,
            "agentCompanyName": "CBRE",
            "agentName": ", ".join(agents),
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": "",
            "saleType": sale_type,
            "businessRatesPerSqft": business_rates,
            "serviceChargePerSqft": service_charge,
        }

        # ---------- FLOOR EXPANSION ---------- #
        if floors:
            expanded = []
            for f in floors:
                obj = base.copy()
                obj["floorName"] = f["floor"]
                obj["sizeFtMin"] = f["minSqft"] or min_sqft
                obj["sizeFtMax"] = f["maxSqft"] or max_sqft
                obj["availability"] = f["status"]
                expanded.append(obj)
            return expanded

        return base

    # ===================== HELPERS ===================== #

    def extract_size_range(self, text):
        if not text:
            return "", ""

        t = text.lower().replace(",", "")
        t = re.sub(r"[–—−]", "-", t)

        m = re.search(r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*sq\s*ft', t)
        if not m:
            return "", ""

        a = float(m.group(1))
        b = float(m.group(2)) if m.group(2) else None
        return (int(a), int(b)) if b else (int(a), int(a))

    def extract_rate(self, text):
        if not text:
            return ""
        m = re.search(r'£\s*(\d+(?:\.\d+)?)', text)
        return float(m.group(1)) if m else ""

    def extract_price_number(self, text, sale_type):
        if sale_type != "For Sale":
            return ""
        t = text.lower()
        if "application" in t:
            return ""
        m = re.search(r'[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)', t)
        if not m:
            return ""
        return str(int(float(m.group(1).replace(",", ""))))

    def extract_postcode(self, text):
        m = re.search(r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b', text.upper())
        return m.group().strip() if m else ""

    def normalize_sale_type(self, text):
        t = text.lower()
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "let" in t:
            return "To Let"
        return ""

    def _clean(self, val):
        return " ".join(val.split()) if val else ""