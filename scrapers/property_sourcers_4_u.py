import re
import requests


class PropertySourcers4UScraper:

    BASE_URL = "https://mypropertymarketplace.co.uk"
    API_URL = "https://whitelabel.admin.theassetmanager.co.uk/api/v1/whitelabel/properties"
    DOMAIN = "https://mypropertymarketplace.co.uk"

    FALLBACK_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhcHBJZCI6IjM0MTE0NjM3IiwibmFtZSI6Im15cHJvcGVydHltYXJrZXRwbGFjZS5jby51ayIsImlhdCI6MTc3MTI3MzM0OTM3OCwiZXhwIjo0MDcwOTA4ODAwMDAwfQ.6Zpv3Id8JEe_bLP1aYpRikt4UrP7zZesR-kNXwBDTDE"

    def __init__(self):
        self.results = []
        self.seen_urls = set()
        self.TOKEN = self._resolve_token()

    # ===================== TOKEN ===================== #

    def _resolve_token(self):
        try:
            token = self._extract_token_from_js()
            if token:
                return token
        except Exception:
            pass

        return self.FALLBACK_TOKEN

    def _extract_token_from_js(self):
        session = requests.Session()
        session.headers.update({
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"
        })

        resp = session.get(self.BASE_URL, timeout=30)
        resp.raise_for_status()

        js_paths = set()
        js_paths.update(re.findall(r'src=["\']([^"\']*\.js[^"\']*)["\']', resp.text))
        js_paths.update(re.findall(r'"([^"]*/_next/static/[^"]*\.js)"', resp.text))
        js_paths.update(re.findall(r'(https?://[^\s"\']+\.js)', resp.text))

        for js_path in js_paths:
            if js_path.startswith("http"):
                js_url = js_path
            elif js_path.startswith("//"):
                js_url = "https:" + js_path
            elif js_path.startswith("/"):
                js_url = self.BASE_URL + js_path
            else:
                js_url = self.BASE_URL + "/" + js_path

            try:
                js_resp = session.get(js_url, timeout=15)
                if js_resp.status_code != 200:
                    continue

                tokens = re.findall(
                    r'eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+',
                    js_resp.text
                )
                if tokens:
                    return tokens[0]

            except Exception:
                continue

        return None

    # ===================== RUN ===================== #

    def run(self):
        page = 1

        while True:
            data = self.fetch_page(page)

            properties = data.get("results", [])
            if not properties:
                break

            for item in properties:
                obj = self.parse_property(item)
                if obj:
                    self.results.append(obj)

            total = data.get("pagination", {}).get("total", 0)

            next_page = data.get("pagination", {}).get("next")
            if not next_page:
                break

            page += 1

        return self.results

    # ===================== API CALL ===================== #

    def fetch_page(self, page):

        headers = {
            "accept": "application/json, text/plain, */*",
            "accept-language": "en-US,en;q=0.9,fr;q=0.8",
            "access-control-allow-methods": "GET,PUT,POST,DELETE,PATCH,OPTIONS",
            "access-control-allow-origin": "*",
            "authorization": f"Bearer {self.TOKEN}",
            "cache-control": "no-cache",
            "content-type": "application/json",
            "origin": "https://mypropertymarketplace.co.uk",
            "pragma": "no-cache",
            "priority": "u=1, i",
            "referer": "https://mypropertymarketplace.co.uk/",
            "sec-ch-ua": '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
            "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
        }

        payload = {
            "sortDate": "Latest",
            "isReserved": False,
            "page": page,
            "limit": 30
        }

        response = requests.post(
            self.API_URL,
            headers=headers,
            json=payload,
            timeout=30
        )

        # Debug if needed
        if response.status_code != 200:
            response.raise_for_status()

        return response.json()

    # ===================== PARSE PROPERTY ===================== #

    def parse_property(self, item):

        listing_url = f"{self.DOMAIN}/property/{item.get('_id')}"

        if listing_url in self.seen_urls:
            return None
        self.seen_urls.add(listing_url)

        display_address = item.get("propertyOf", "")
        size_ft, size_ac = self.extract_size(item.get("floorsqft", ""))

        obj = {
            "listingUrl": listing_url,
            "displayAddress": display_address,
            "price": str(item.get("price", "")),
            "propertySubType": item.get("strategy", ""),
            "propertyImage": [img["url"] for img in item.get("images", [])],
            "detailedDescription": "",
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": [],
            "agentCompanyName": "Property Sourcers 4 U",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": item.get("tenureType", ""),
            "saleType": "For Sale",
        }
        return obj

    # ===================== HELPERS ===================== #

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(r'(\d+(?:\.\d+)?)\s*sq', text)
        if m:
            size_ft = round(float(m.group(1)), 3)

        m = re.search(r'(\d+(?:\.\d+)?)\s*ac', text)
        if m:
            size_ac = round(float(m.group(1)), 3)

        return size_ft, size_ac

    def extract_postcode(self, text):
        if not text:
            return ""

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        t = text.upper()
        m = re.search(FULL, t) or re.search(PARTIAL, t)
        return m.group() if m else ""