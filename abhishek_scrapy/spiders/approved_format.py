# import json
# from selenium import webdriver
# from selenium.webdriver.common.by import By
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC
# from selenium.webdriver.chrome.options import Options
# from lxml import html
# import csv
# import re
# from datetime import datetime
# from urllib.parse import urljoin
# import time
# from selenium.webdriver.chrome.service import Service
# from webdriver_manager.chrome import ChromeDriverManager


# class LSHPropertyScraper:
#     def __init__(self):
#         self.base_url = "https://www.lsh.co.uk"

#         chrome_options = Options()
#         chrome_options.add_argument("--headless=new")
#         chrome_options.add_argument("--no-sandbox")
#         chrome_options.add_argument("--disable-dev-shm-usage")
#         chrome_options.add_argument("--disable-gpu")
#         chrome_options.add_argument("--disable-extensions")
#         chrome_options.add_argument("--disable-background-networking")
#         chrome_options.add_argument("--blink-settings=imagesEnabled=false")
#         chrome_options.add_argument(
#             "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"
#         )

#         service = Service(ChromeDriverManager().install())
#         self.driver = webdriver.Chrome(service=service, options=chrome_options)

#         # IMPORTANT: prevent Selenium hang
#         self.driver.set_page_load_timeout(30)

#     def restart_driver(self):
#         try:
#             self.driver.quit()
#         except:
#             pass
#         self.__init__()

#     def scroll_to_load_all_properties(self):
#         print("Loading all properties via infinite scroll...")
#         last_height = self.driver.execute_script("return document.body.scrollHeight")

#         while True:
#             self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
#             time.sleep(2)
#             new_height = self.driver.execute_script("return document.body.scrollHeight")
#             if new_height == last_height:
#                 break
#             last_height = new_height

#     def get_listing_urls(self, search_url):
#         print("Fetching property listing URLs...")
#         try:
#             self.driver.get(search_url)
#             WebDriverWait(self.driver, 10).until(
#                 EC.presence_of_element_located((By.CSS_SELECTOR, 'div.property'))
#             )

#             self.scroll_to_load_all_properties()

#             tree = html.fromstring(self.driver.page_source)
#             links = tree.xpath('//a[contains(@href, "/find/properties/")]/@href')

#             urls = []
#             for link in links:
#                 full = urljoin(self.base_url, link)
#                 if '?' not in full and full.count('/') >= 6 and full not in urls:
#                     urls.append(full)

#             print(f"Found {len(urls)} property listings")
#             return urls

#         except Exception as e:
#             print("Error fetching listing URLs:", e)
#             return []

#     def extract_postcode(self, text):
#         match = re.search(r'([A-Z]+),\s*([A-Z]{1,2}\s*\d{1,2})$', text, re.IGNORECASE)

#         if match:
#             result = f"{match.group(1)[-3:].upper()}, {match.group(2).replace(' ', '').upper()}"
#             return result
#         else:
#             return ''
        
#     # def extract_postcode(self, text):
#     #     FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
#     #     PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'
#     #     text = text.upper()
#     #     match = re.search(FULL ,text) or re.search(PARTIAL,text)
#     #     if match:
#     #         return match.group().upper().strip()
#     #     else:
#     #         return ''   corrected format


#     def scrape_property_details(self, url, retries=2):
#         print(f"Scraping: {url}")

#         for attempt in range(retries + 1):
#             try:
#                 try:
#                     self.driver.get(url)
#                 except:
#                     self.driver.execute_script("window.stop();")

#                 time.sleep(2)
#                 tree = html.fromstring(self.driver.page_source)

#                 data = {
#                     'listingUrl': url,
#                     'displayAddress': '',
#                     'price': '',
#                     'propertySubType': '',
#                     'propertyImage': '',
#                     'detailedDescription': '',
#                     'sizeFt': '',
#                     'sizeAc': '',
#                     'postalCode': '',
#                     'brochureUrl': '',
#                     'agentCompanyName': 'LSH',
#                     'agentName': '',
#                     'agentCity': '',
#                     'agentState': '',
#                     'agentEmail': '',
#                     'agentPhone': '',
#                     'agentStreet': '',
#                     'agentPostcode': '',
#                     'tenure': '',
#                     'saleType': ''
#                 }

#                 address = tree.xpath("//p[@class='kilo caps']/text()")
#                 if address:
#                     data['displayAddress'] = ' '.join(a.strip() for a in address)
#                     # data['displayAddress'] = address[0].strip() corrected way
#                     data['postalCode'] = self.extract_postcode(data['displayAddress'])

#                 sale = tree.xpath('//span[contains(text(),"Types:")]/following-sibling::span[1]/text()')
#                 if sale:
#                     sale = sale[0].lower() ## sale[0].strip().lower()  corrected way
#                     data['saleType'] = 'For Sale' if 'sale' in sale else 'To Let'
#                     data['propertySubType'] = sale

#                 size = tree.xpath('//span[contains(text(),"Size:")]/following-sibling::span[1]/text()')
#                 if size:
#                     if 'ac' in size[0].lower():
#                         data['sizeAc'] = size[0]
#                     else:
#                         data['sizeFt'] = size[0]

#                 tenure = tree.xpath('//span[contains(text(),"Tenure:")]/following-sibling::span[1]/text()')
#                 if tenure:
#                     data['tenure'] = tenure[0]

#                 desc = tree.xpath("//p[@class='ws-pl']/text()")
#                 if desc:
#                     data['detailedDescription'] = ' '.join(desc)

#                 brochure = tree.xpath('//a[contains(@href,".pdf")]/@href')
#                 if brochure:
#                     data['brochureUrl'] = urljoin(self.base_url, brochure[0])

#                 image_urls = tree.xpath('//div[contains(@class, "gallery")]//img/@src | //img[contains(@class, "gallery")]/@src | //div[contains(@class, "property-hero")]//img/@src')
#                 if image_urls:
#                     image_urls = [img for img in image_urls if 'hive.agencypilot.com' in img or '/uploads/' in img]
#                     data['propertyImage'] = str(image_urls)

#                 agent_names = tree.xpath("//p[@class='name']/span/text()")
#                 if agent_names:
#                     data['agentName'] = '| '.join(agent_names)  #only take the first agent not all agent and same way take other detail of same agent first agent in case if there are multiple agents  , correct way is    data['agentName'] = agent_names[0] if isinstance(agent_names , list) else agent_name 

#                 agent_numbers = tree.xpath("//div[@class='profile-card__details']//a[contains(@href, 'tel')]/text()")
#                 if agent_numbers:
#                     data['agentPhone'] = '| '.join(agent_numbers)
#                 print("data === >>",data)
#                 return data

#             except Exception as e:
#                 print(f"Retry {attempt+1} failed:", e)
#                 if attempt == retries:
#                     return None
#                 time.sleep(2)

#     def scrape_all_properties(self, search_url):
#         date_str = datetime.now().strftime('%Y-%m-%d')
#         output_file = f"lsh_properties_{date_str}.csv"

#         urls = self.get_listing_urls(search_url)
#         if not urls:
#             return

#         fields = [
#             'listingUrl','displayAddress','price','propertySubType',
#             'propertyImage','detailedDescription','sizeFt','sizeAc',
#             'postalCode','brochureUrl','agentCompanyName','agentName',
#             'agentCity','agentState','agentEmail','agentPhone',
#             'agentStreet','agentPostcode','tenure','saleType'
#         ]

#         with open(output_file, 'w', newline='', encoding='utf-8') as f:
#             writer = csv.DictWriter(f, fieldnames=fields)
#             writer.writeheader()

#             for i, url in enumerate(urls, 1):
#                 print(f"Processing {i}/{len(urls)}")

#                 if i % 40 == 0:
#                     print("Restarting browser")
#                     self.restart_driver()

#                 row = self.scrape_property_details(url)
#                 if row:
#                     writer.writerow(row)
#                     f.flush()

#         print(f"\n✓ Completed. Saved to {output_file}")

#     def cleanup(self):
#         try:
#             self.driver.quit()
#         except:
#             pass


# if __name__ == "__main__":
#     print("Starting scraper...")
#     search_url = "https://www.lsh.co.uk/find/properties?action=search&group=3825744134714e28915acb0b63c32a6e|df0743002d4547bdbc8da25b6b372558|64f679ff61ec4ef8a5285c44261d69fd|d680bad576b84938b2fa98de2811ae1c|3b565ef645d84855a41281079f8497d3|9eb51a72c86746a987b2f97d2e9f4ca9|0b0fb49cb45a474eb28612c6feb102c5&tenure=51d529b458644e2ebb17abb713bae042|bf299c8b766743869efcf736e1fbba84"
#     scraper = LSHPropertyScraper()
#     scraper.scrape_all_properties(search_url)
#     scraper.cleanup()
