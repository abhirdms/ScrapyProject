# import scrapy
# import re


# class BuildoutApiSpider(scrapy.Spider):
#     name = "buildout_api"
#     allowed_domains = ["buildout.nmrk.com"]

#     start_urls = [
#         "https://buildout.nmrk.com/plugins/"
#         "267fecb3c0aa79175cdde4a3ab3e74e9403a90bd/"
#         "inventory?page=0&light_view=true"
#     ]

#     headers = {
#         "User-Agent": "Mozilla/5.0",
#         "Accept": "application/json",
#         "X-Requested-With": "XMLHttpRequest",
#         "Referer": "https://www.nmrk.com/",
#     }

#     # ===============================
#     # MAIN PARSER
#     # ===============================
#     def parse(self, response):
#         data = response.json()
#         items = data.get("inventory", [])

#         for item in items:
#             yield self.parse_item(item)

#         # pagination: page++
#         if items:
#             current_page = int(response.url.split("page=")[1].split("&")[0])
#             next_page = current_page + 1
#             next_url = response.url.replace(
#                 f"page={current_page}", f"page={next_page}"
#             )

#             yield scrapy.Request(
#                 url=next_url,
#                 headers=self.headers,
#                 callback=self.parse,
#             )

#     # ===============================
#     # ITEM BUILDER
#     # ===============================
#     def parse_item(self, item):
#         return {
#             "listingUrl": self.get_listing_url(item),
#             "displayAddress": self.get_display_address(item),
#             "price": self.get_price(item),
#             "propertySubType": self.get_property_sub_type(item),
#             "propertyImage": self.get_property_images(item),
#             "detailedDescription": self.get_description(item),
#             "sizeFt": self.get_size_sqft(item),
#             "sizeAc": self.get_size_acres(item),
#             "postalCode": self.get_postcode(item),
#             "brochureUrl": self.get_brochure_url(item),
#             "agentCompanyName": self.get_agent_company(item),
#             "agentName": self.get_agent_name(item),
#             "agentCity": self.get_agent_city(item),
#             "agentEmail": self.get_agent_email(item),
#             "agentPhone": self.get_agent_phone(item),
#             "agentStreet": self.get_agent_street(item),
#             "agentPostcode": self.get_agent_postcode(item),
#             "tenure": self.get_tenure(item),
#             "saleType": self.get_sale_type(item),
#         }

#     # ===============================
#     # AGENT SELECTION (IMPORTANT)
#     # ===============================
#     def get_primary_agent(self, item):
#         """
#         If multiple broker_contacts exist:
#         - pick ONE agent
#         - all agent-related fields must come from this agent only
#         """
#         contacts = item.get("broker_contacts", [])
#         if not contacts:
#             return None
#         return contacts[0]

#     # ===============================
#     # FIELD METHODS (ONE PER REQUIREMENT)
#     # ===============================
#     def get_listing_url(self, item):
#         return item.get("show_link")

#     def get_display_address(self, item):
#         return item.get("address_one_line")

#     def get_price(self, item):
#         if not item.get("sale"):
#             return None

#         for label, value in item.get("index_attributes", []):
#             if label.lower() == "price":
#                 return self.extract_numeric_price(value)
#         return None

#     def get_property_sub_type(self, item):
#         return item.get("property_sub_type_name")

#     def get_property_images(self, item):
#         images = []
#         if item.get("photo_url"):
#             images.append(item["photo_url"])
#         if item.get("large_thumbnail_url"):
#             images.append(item["large_thumbnail_url"])
#         return images

#     def get_description(self, item):
#         return item.get("photo_description")

#     def get_size_sqft(self, item):
#         return self.extract_numeric(item.get("size_summary"))

#     def get_size_acres(self, item):
#         return None  # not provided by API

#     def get_postcode(self, item):
#         return item.get("zip")

#     def get_brochure_url(self, item):
#         return item.get("pdf_url")

#     def get_agent_company(self, item):
#         return "LSH"

#     def get_agent_name(self, item):
#         agent = self.get_primary_agent(item)
#         return agent.get("name") if agent else None

#     def get_agent_city(self, item):
#         return item.get("city")

#     def get_agent_email(self, item):
#         agent = self.get_primary_agent(item)
#         return agent.get("email") if agent else None

#     def get_agent_phone(self, item):
#         agent = self.get_primary_agent(item)
#         return agent.get("phone") if agent else None

#     def get_agent_street(self, item):
#         return item.get("address")

#     def get_agent_postcode(self, item):
#         return item.get("zip")

#     def get_tenure(self, item):
#         return "Freehold" if item.get("sale") else "Leasehold"

#     def get_sale_type(self, item):
#         return "For Sale" if item.get("sale") else "To Let"

#     # ===============================
#     # HELPERS
#     # ===============================
#     def extract_numeric_price(self, text):
#         if not text:
#             return None
#         numbers = re.findall(r"\d+", text.replace(",", ""))
#         return int(numbers[0]) if numbers else None

#     def extract_numeric(self, text):
#         if not text:
#             return None
#         numbers = re.findall(r"\d+", text.replace(",", ""))
#         return int(numbers[0]) if numbers else None
