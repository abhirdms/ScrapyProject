import scrapy
import re
from urllib.parse import urlparse, parse_qs, urlencode


class GeraldEveSpider(scrapy.Spider):
    name = "GeraldEve"
    allowed_domains = ["buildout.nmrk.com"]

    start_urls = [
        "https://buildout.nmrk.com/plugins/"
        "267fecb3c0aa79175cdde4a3ab3e74e9403a90bd/inventory"
        "?lat_min=&lat_max=&lng_min=&lng_max="
        "&page=0"
        "&light_view=true"
        "&placesAutoComplete="
        "&q[type_use_offset_eq_any][]="
        "&q[sale_or_lease_eq]="
        "&q[city_eq_any][]="
        "&q[has_broker_ids][]="
        "&q[listings_data_max_space_available_on_market_gteq]="
        "&q[listings_data_min_space_available_on_market_lteq]="
        "&q[property_use_id_eq_any][]="
        "&q[total_sf_available_gteq]="
        "&q[total_sf_available_lteq]="
        "&q[s][]=sale_price+desc"
    ]

    headers = {
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/144.0.0.0 Safari/537.36"
        ),
        "Referer": (
            "https://buildout.nmrk.com/plugins/"
            "267fecb3c0aa79175cdde4a3ab3e74e9403a90bd/"
            "www.nmrk.com/inventory/?pluginId=0&iframe=true"
        ),
    }

    # ===============================
    # ENTRY POINT (HEADERS APPLIED)
    # ===============================
    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url=url,
                headers=self.headers,
                callback=self.parse
            )

    # ===============================
    # MAIN PARSER
    # ===============================
    def parse(self, response):
        data = response.json()
        items = data.get("inventory", [])

        for item in items:
            yield self.parse_item(item)

        # pagination: stop when API returns empty list
        if items:
            next_url = self.get_next_page_url(response.url)
            yield scrapy.Request(
                url=next_url,
                headers=self.headers,
                callback=self.parse
            )

    # ===============================
    # ITEM BUILDER
    # ===============================
    def parse_item(self, item):
        return {
            "listingUrl": self.get_listing_url(item),
            "displayAddress": self.get_display_address(item),
            "price": self.get_price(item),
            "propertySubType": self.get_property_sub_type(item),
            "propertyImage": self.get_property_images(item),
            "detailedDescription": self.get_description(item),
            "sizeFt": self.get_size_sqft(item),
            "sizeAc": self.get_size_acres(item),
            "postalCode": self.get_postcode(item),
            "brochureUrl": self.get_brochure_url(item),
            "agentCompanyName": self.get_agent_company(item),
            "agentName": self.get_agent_name(item),
            "agentCity": self.get_agent_city(item),
            "agentEmail": self.get_agent_email(item),
            "agentPhone": self.get_agent_phone(item),
            "agentStreet": self.get_agent_street(item),
            "agentPostcode": self.get_agent_postcode(item),
            "tenure": self.get_tenure(item),
            "saleType": self.get_sale_type(item),
        }

    # ===============================
    # AGENT SELECTION (SINGLE AGENT)
    # ===============================
    def get_primary_agent(self, item):
        contacts = item.get("broker_contacts", [])
        return contacts[0] if contacts else None

    # ===============================
    # FIELD METHODS
    # ===============================
    def get_listing_url(self, item):
        return item.get("show_link")

    def get_display_address(self, item):
        value = item.get("address_one_line")
        return value.strip() if value else None

    def get_price(self, item):
        if not item.get("sale"):
            return None
        for label, value in item.get("index_attributes", []):
            if label.lower() == "price":
                return self.extract_numeric_price(value)
        return None

    def get_property_sub_type(self, item):
        value = item.get("property_sub_type_name")
        return value.strip() if value else None

    def get_property_images(self, item):
        images = []
        if item.get("photo_url"):
            images.append(item["photo_url"].strip())
        if item.get("large_thumbnail_url"):
            images.append(item["large_thumbnail_url"].strip())
        return images

    def get_description(self, item):
        value = item.get("photo_description")
        return value.strip() if value else None

    def get_size_sqft(self, item):
        return self.extract_numeric(item.get("size_summary"))

    def get_size_acres(self, item):
        return None

    def get_postcode(self, item):
        # Try extracting from address first (most reliable)
        value = item.get("zip")
        return self.extract_postcode(value)

    def get_brochure_url(self, item):
        value = item.get("pdf_url")
        return value.strip() if value else None

    def get_agent_company(self, item):
        return "LSH"

    def get_agent_name(self, item):
        agent = self.get_primary_agent(item)
        value = agent.get("name") if agent else None
        return value.strip() if value else None

    def get_agent_city(self, item):
        value = item.get("city")
        return value.strip() if value else None

    def get_agent_email(self, item):
        agent = self.get_primary_agent(item)
        value = agent.get("email") if agent else None
        return value.strip() if value else None

    def get_agent_phone(self, item):
        agent = self.get_primary_agent(item)
        value = agent.get("phone") if agent else None
        return value.strip() if value else None

    def get_agent_street(self, item):
        value = item.get("address")
        return value.strip() if value else None

    def get_agent_postcode(self, item):
        value = item.get("zip")
        return self.extract_postcode(value)

    def get_tenure(self, item):
        return "Freehold" if item.get("sale") else "Leasehold"

    def get_sale_type(self, item):
        return "For Sale" if item.get("sale") else "To Let"

    # ===============================
    # HELPERS
    # ===============================
    def extract_postcode(self, text):
        """
        Extract UK postcode from any text.
        Supports FULL and PARTIAL postcodes.
        """
        if not text:
            return None

        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        text = text.upper()

        match = re.search(FULL, text) or re.search(PARTIAL, text)
        if match:
            return match.group().upper().strip()

        return None



    def extract_numeric_price(self, text):
        if not text:
            return None
        nums = re.findall(r"\d+", text.replace(",", ""))
        return int(nums[0]) if nums else None

    def extract_numeric(self, text):
        if not text:
            return None
        nums = re.findall(r"\d+", text.replace(",", ""))
        return int(nums[0]) if nums else None

    def get_next_page_url(self, url):
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        current_page = int(params.get("page", [0])[0])
        params["page"] = [str(current_page + 1)]

        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}?{urlencode(params, doseq=True)}"
