# import scrapy
# from scrapy.selector import Selector

# # ===============================
# # OPTIONAL: Selenium imports
# # UNCOMMENT ONLY for JS websites
# # ===============================
# # from selenium import webdriver
# # from selenium.webdriver.chrome.options import Options
# # from selenium.webdriver.chrome.service import Service
# # from webdriver_manager.chrome import ChromeDriverManager
# # import time


# class BaseTemplateSpider(scrapy.Spider):
#     """
#     SCRAPY UNIVERSAL TEMPLATE

#     Supports:
#     1. Static HTML websites
#     2. Header-protected websites
#     3. API-based websites
#     4. JavaScript-rendered websites (Selenium)

#     Usage:
#     - Edit CONFIG SECTION
#     - Edit parse_item()
#     - Comment / uncomment blocks as needed
#     """

#     # ===============================
#     # BASIC CONFIG (EDIT THIS)
#     # ===============================
#     name = "template_code"
#     allowed_domains = ["example.com"]              # 🔁 EDIT
#     start_urls = ["https://example.com"]            # 🔁 EDIT

#     # ===============================
#     # HEADERS (OPTIONAL)
#     # COMMENT headers if not required
#     # ===============================
#     headers = {
#         "User-Agent": (
#             "Mozilla/5.0 (X11; Linux x86_64) "
#             "AppleWebKit/537.36 (KHTML, like Gecko) "
#             "Chrome/120.0.0.0 Safari/537.36"
#         ),
#         "Accept": "*/*",
#         "Accept-Language": "en-US,en;q=0.9",
#         "Referer": "https://google.com",
#     }

#     # ===============================
#     # ENTRY POINT
#     # ===============================
#     def start_requests(self):
#         for url in self.start_urls:

#             # 🔹 CASE 1 & 2: HTML or API (Scrapy)
#             yield scrapy.Request(
#                 url=url,
#                 callback=self.parse,
#                 headers=self.headers,   # COMMENT if headers not needed
#             )

#             # 🔹 CASE 3: JavaScript Website (Selenium)
#             # yield scrapy.Request(
#             #     url=url,
#             #     callback=self.parse_with_selenium,
#             #     dont_filter=True
#             # )

#     # ===============================
#     # MAIN PARSER (HTML OR API)
#     # ===============================
#     def parse(self, response):
#         """
#         TEMPLATE PARSER

#         HTML website  → use response.css / xpath
#         API website   → use response.json()

#         Choose ONE approach below.
#         """

#         # ===============================
#         # 🔹 OPTION A: HTML PARSING
#         # ===============================
#         # items = response.css("CSS_SELECTOR")   # 🔁 EDIT
#         # for item in items:
#         #     yield self.parse_item(item)

#         # next_page = response.css("NEXT_PAGE_SELECTOR::attr(href)").get()
#         # if next_page:
#         #     yield response.follow(
#         #         next_page,
#         #         callback=self.parse,
#         #         headers=self.headers,
#         #     )

#         # ===============================
#         # 🔹 OPTION B: API (JSON) PARSING
#         # ===============================
#         # data = response.json()
#         # items = data.get("ITEMS_KEY", [])       # 🔁 EDIT
#         # for item in items:
#         #     yield self.parse_item(item)

#         # next_url = data.get("NEXT_PAGE_URL")    # 🔁 EDIT
#         # if next_url:
#         #     yield scrapy.Request(
#         #         url=next_url,
#         #         callback=self.parse,
#         #         headers=self.headers,
#         #     )

#         pass  # REMOVE after enabling one option

#     # ===============================
#     # ITEM PARSER (EDIT PER WEBSITE)
#     # ===============================
#     def parse_item(self, item):
#         """
#         EDIT THIS METHOD ONLY.
#         Return a normalized dict.
#         """

#         # 🔁 EXAMPLES (DELETE & CUSTOMIZE)
#         # HTML item:
#         # return {
#         #     "field_1": item.css("::text").get(),
#         # }

#         # API item:
#         # return {
#         #     "field_1": item.get("key"),
#         # }

#         return {}

#     # ===============================
#     # SELENIUM PARSER (JS WEBSITES)
#     # ===============================
#     # def parse_with_selenium(self, response):
#     #     self.logger.info("Using Selenium (JS-rendered site)")
#     #
#     #     chrome_options = Options()
#     #     chrome_options.add_argument("--headless")
#     #     chrome_options.add_argument("--no-sandbox")
#     #     chrome_options.add_argument("--disable-dev-shm-usage")
#     #
#     #     driver = webdriver.Chrome(
#     #         service=Service(ChromeDriverManager().install()),
#     #         options=chrome_options
#     #     )
#     #
#     #     driver.get(response.url)
#     #     time.sleep(3)
#     #
#     #     selector = Selector(text=driver.page_source)
#     #
#     #     items = selector.css("CSS_SELECTOR")   # 🔁 EDIT
#     #     for item in items:
#     #         yield self.parse_item(item)
#     #
#     #     driver.quit()
