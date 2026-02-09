import re
import requests
from urllib.parse import urljoin
from lxml import html


class GVAScraper:
    API_URL = "https://pse-api.sharplaunch.com/data"
    API_KEY = "17e025f5b7404cba77f738c9f99394c9"
    DOMAIN = "https://www.avisonyoung.co.uk/"

    def __init__(self):
        self.results = []

    # ---------------- RUN ---------------- #

    def run(self):
        headers = {
            "accept": "application/json, text/plain, */*",
            "origin": "https://www.avisonyoung.co.uk",
            "referer": "https://www.avisonyoung.co.uk/properties",
            "user-agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/144.0.0.0 Safari/537.36"
            ),
            "x-api-key": self.API_KEY,
        }

        params = {
            "entity": "website",
            "status": "active,escrow",
        }

        resp = requests.get(self.API_URL, headers=headers, params=params, timeout=30)
        resp.raise_for_status()

        data = resp.json()

        for item in data.get("items", []):
            try:
                self.results.append(self.parse_item(item))
            except Exception:
                continue

        return self.results

    # ---------------- PARSER ---------------- #

    def parse_item(self, item):

        # -------- SIZE (USING SAME METHOD AS OTHER SCRAPERS) -------- #

        size_ft, size_ac = self.extract_size_from_api(item)


        # -------- PRICE -------- #
        price = self.extract_sale_price(item)
        listing_url = item.get("external_url", "")

        tree = self.get_listing_tree(listing_url)
        brochure_url = self.extract_brochure_url_from_tree(tree, listing_url)

        agent_name, agent_email, agent_phone = self.extract_first_agent_from_tree(tree)



        images = self.extract_property_images_from_tree(tree, listing_url)

        tenure = self.extract_tenure_from_transaction(item)



        # -------- SALE TYPE -------- #
        transactions = item.get("transaction", []) or []


        sale_type = ""
        if "lease" in transactions or "sublease" in transactions:
            sale_type = "To Let"
        if "sale" in transactions:
            sale_type = "For Sale"


        obj = {
            "listingUrl": listing_url,

            "displayAddress": item.get("address", "").strip(),

            "price": price,

            "propertySubType": ", ".join(item.get("type", [])),

            "propertyImage": images,


            "detailedDescription": item.get("description", ""),

            "sizeFt": size_ft,
            "sizeAc": size_ac,

            "postalCode": item.get("zip", ""),

            "brochureUrl": brochure_url,

            "agentCompanyName": "Avison Young",
            "agentCity": "",
            "agentName": agent_name,
            "agentEmail": agent_email,
            "agentPhone": agent_phone,


            "agentStreet": "",
            "agentPostcode": "",

            "tenure": tenure,
            "saleType": sale_type,
        }
        return obj
    
    def extract_tenure_from_transaction(self, item):
        """
        Determine tenure from transaction values.

        Rules:
        - No transaction -> Freehold
        - lease / sublease present -> Leasehold
        - only sale -> Freehold
        """
        transactions = item.get("transaction", []) or []

        # Normalize to lowercase
        transactions = [t.lower() for t in transactions]

        if not transactions:
            return "Freehold"

        if "lease" in transactions or "sublease" in transactions:
            return "Leasehold"

        return ""

    
    def extract_first_agent_from_tree(self, tree):
        """
        Extract FIRST agent details using the actual Avison Young HTML structure.
        Returns: (agent_name, agent_email, agent_phone)
        """
        if tree is None:
            return "", "", ""

        root = tree.xpath("(//div[contains(@class,'team-member__container')])[1]")
        if not root:
            return "", "", ""

        root = root[0]

        agent_name = ""
        agent_email = ""
        agent_phone = ""

        # ---- NAME ----
        name = root.xpath(".//h4[contains(@class,'team-member__name')]/text()")
        if name:
            agent_name = name[0].strip()

        # ---- EMAIL (TEXT FIRST, mailto fallback just in case) ----
        email_text = root.xpath(
            ".//div[contains(@class,'team-member__email')]//a/text()"
        )
        if email_text and email_text[0].strip():
            agent_email = email_text[0].strip()
        else:
            email_href = root.xpath(
                ".//div[contains(@class,'team-member__email')]//a/@href"
            )
            if email_href and email_href[0].startswith("mailto:"):
                agent_email = email_href[0].replace("mailto:", "").strip()

        # ---- PHONE (FIRST ONLY) ----
        phone = root.xpath(
            ".//div[contains(@class,'team-member__phone')]//a[1]/text()"
        )
        if phone:
            agent_phone = phone[0].strip()

        return agent_name, agent_email, agent_phone





    def extract_brochure_url_from_tree(self, tree, base_url):
        if tree is None:
            return []

        urls = tree.xpath(
            "//div[contains(@class,'availability__row')]//a[@href]/@href"
        )

        return [
            urljoin(base_url, u.strip())
            for u in urls
            if u and u.strip()
        ]



    def extract_size_from_api(self, item):
        """
        Store size strictly based on total_surface_unit.
        - sqft / ft / ft2 -> sizeFt
        - ac / acre / acres -> sizeAc
        - NO conversion
        """
        size_ft = ""
        size_ac = ""

        unit = (item.get("total_surface_unit") or "").lower()
        value = item.get("total_surface")

        if value in (None, "", 0):
            return "", ""

        try:
            value = float(value)
            value = int(value) if value.is_integer() else value
        except (TypeError, ValueError):
            return "", ""

        # ---- SQ FT ----
        if unit in ("sqft", "ft", "ft2"):
            size_ft = value

        # ---- ACRES ----
        elif unit in ("ac", "acre", "acres"):
            size_ac = value

        return size_ft, size_ac


    def extract_property_images_from_tree(self, tree, base_url):
        """
        Extract gallery images from already-built lxml tree.
        """
        if tree is None:
            return []

        image_urls = tree.xpath(
            "//div[contains(@class,'__js-gallery')]"
            "//button[@data-fancybox='section-gallery']/@data-src"
        )

        return [
            urljoin(base_url, img.strip())
            for img in image_urls
            if img and img.strip()
        ]





    def get_listing_tree(self, listing_url):
        """
        Fetch listing page and return lxml HTML tree.
        Reusable for all attribute extraction.
        """
        if not listing_url:
            return None

        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/144.0.0.0 Safari/537.36"
                )
            }

            resp = requests.get(listing_url, headers=headers, timeout=30)
            if resp.status_code != 200:
                return None

            return html.fromstring(resp.text)

        except Exception:
            return None


    def extract_sale_price(self, item):
        """
        Return numeric sale price ONLY if transaction contains 'sale'.
        Otherwise return empty string "".
        """
        transactions = item.get("transaction", []) or []

        if "sale" not in transactions:
            return ""   # ✅ NO COMMA

        sale_price = item.get("sale_price")

        if sale_price is None or sale_price == "":
            return ""

        try:
            price = float(sale_price)
            return int(price) if price.is_integer() else price
        except (TypeError, ValueError):
            return ""


    def _normalize_acre(self, val):
        if val == "" or val is None:
            return ""
        return int(val) if float(val).is_integer() else round(val, 3)
