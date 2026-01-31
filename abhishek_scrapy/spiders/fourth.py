# import scrapy
# from scrapy.selector import Selector
# from selenium import webdriver
# from selenium.webdriver.chrome.options import Options
# from selenium.webdriver.chrome.service import Service
# from webdriver_manager.chrome import ChromeDriverManager
# import time

# class JsSpider(scrapy.Spider):
#     name = "js_spider"
#     allowed_domains = ["example.com"]
#     start_urls = ["https://example.com"]

#     def parse(self, response):
#         chrome_options = Options()
#         chrome_options.add_argument("--headless")
#         chrome_options.add_argument("--no-sandbox")

#         driver = webdriver.Chrome(
#             service=Service(ChromeDriverManager().install()),
#             options=chrome_options
#         )

#         driver.get(response.url)
#         time.sleep(3)

#         selector = Selector(text=driver.page_source)

#         items = selector.css("CSS_SELECTOR")   # 🔁 CHANGE
#         for item in items:
#             yield {
#                 "field_1": item.css("::text").get(),  # 🔁 CHANGE
#             }

#         driver.quit()
