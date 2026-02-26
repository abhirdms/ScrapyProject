import re
import requests
from urllib.parse import urljoin


class EverardColeScraper:
    API_URL = (
        "https://everardcole.co.uk/DesktopModules/"
        "EverardColeServices/API/properties/retrieve_properties"
        "?$filter=published+eq+1"
        "&$expand=property_images,property_documents,"
        "property_types/prop_type,property_tenures/prop_tenure,"
        "property_persons/person1"
    )

    DOMAIN = "https://everardcole.co.uk"

    def __init__(self):
        self.results = []

    # ===================== RUN ===================== #

    def run(self):
        headers = {
            "accept": "application/json, text/plain, */*",
            "origin": self.DOMAIN,
            "referer": f"{self.DOMAIN}/properties",
            "user-agent": "Mozilla/5.0"
        }

        response = requests.post(self.API_URL, headers=headers)
        response.raise_for_status()

        data = response.json()

        for item in data:
            obj = self.parse_property(item)
            if obj:
                self.results.append(obj)

        return self.results

    # ===================== PARSE ===================== #

    def parse_property(self, item):

        # ---------- URL ---------- #
        slug = item.get("url")
        listing_url = urljoin(self.DOMAIN, f"/properties/{slug}") if slug else ""

        # ---------- ADDRESS ---------- #
        address_parts = [
            item.get("premise"),
            item.get("street"),
            item.get("town"),
            item.get("city"),
            item.get("postcode")
        ]
        display_address = ", ".join([p for p in address_parts if p])

        # ---------- SALE TYPE ---------- #
        status = (item.get("status") or "").lower()
        if "offer" in status:
            sale_type = "For Sale"
        elif item.get("sales_lettings") == 1:
            sale_type = "For Sale"
        else:
            sale_type = "To Let"

        # ---------- PRICE ---------- #
        price = ""
        if sale_type == "For Sale" and item.get("price"):
            price = str(int(float(item["price"])))

        # ---------- PROPERTY TYPES ---------- #
        property_types = [
            pt["prop_type"]["name"]
            for pt in item.get("property_types", [])
            if pt.get("prop_type")
        ]
        property_sub_type = ", ".join(property_types)

        # ---------- TENURE ---------- #
        tenures = [
            t["prop_tenure"]["name"]
            for t in item.get("property_tenures", [])
            if t.get("prop_tenure")
        ]
        tenure = ", ".join(tenures)

        # ---------- DESCRIPTION ---------- #
        description_parts = [
            self.clean_html(item.get("description")),
            self.clean_html(item.get("location_details")),
            self.clean_html(item.get("planning")),
            self.clean_html(item.get("fixtures")),
            self.clean_html(item.get("measurements")),
            self.clean_html(item.get("tenure")),
            self.clean_html(item.get("rates_charges")),
        ]
        detailed_description = " ".join(
            p for p in description_parts if p
        )

        # ---------- SIZE ---------- #
        measurements = item.get("measurements") or ""
        keypoints = item.get("keypoints") or ""

        size_ft, size_ac = self.extract_size(measurements + " " + keypoints)

        # ---------- IMAGES ---------- #
        property_images = []
        for img in item.get("property_images", []):
            filename = img.get("filename")
            if filename:
                property_images.append(
                    urljoin(self.DOMAIN, f"/DesktopModules/EverardColeServices/API/media/download/{filename}")
                )

        # ---------- BROCHURES ---------- #
        brochure_urls = []
        for doc in item.get("property_documents", []):
            filename = doc.get("filename")
            if filename:
                brochure_urls.append(
                    urljoin(self.DOMAIN, f"/DesktopModules/EverardColeServices/API/media/download/{filename}")
                )

        # ---------- AGENT ---------- #
        agent_name = ""
        agent_email = ""
        agent_phone = ""

        persons = item.get("property_persons", [])
        if persons and persons[0].get("person1"):
            person = persons[0]["person1"]
            agent_name = person.get("name", "")
            agent_email = person.get("email", "")
            agent_phone = person.get("telephone", "")

        obj = {
            "listingUrl": listing_url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": item.get("postcode", ""),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Everard Cole",
            "agentName": agent_name,
            "agentCity": item.get("city", ""),
            "agentEmail": agent_email,
            "agentPhone": agent_phone,
            "agentStreet": item.get("street", ""),
            "agentPostcode": item.get("postcode", ""),
            "tenure": tenure,
            "saleType": sale_type,
        }

        print("*****" * 10)
        print(obj)
        print("*****" * 10)

        return obj

    # ===================== HELPERS ===================== #

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower()
        text = text.replace(",", "")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        # SQ FT
        m = re.search(r'(\d+(?:\.\d+)?)\s*(sq\.?\s*ft|ft)', text)
        if m:
            size_ft = round(float(m.group(1)), 3)

        # ACRES
        m = re.search(r'(\d+(?:\.\d+)?)\s*(acres?|acre)', text)
        if m:
            size_ac = round(float(m.group(1)), 3)

        return size_ft, size_ac

    def clean_html(self, html_text):
        if not html_text:
            return ""
        clean = re.sub("<.*?>", " ", html_text)
        return " ".join(clean.split())