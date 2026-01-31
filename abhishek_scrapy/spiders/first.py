import scrapy

class StaticHtmlSpider(scrapy.Spider):
    name = "static_html"
    allowed_domains = ["example.com"]
    start_urls = ["https://example.com"]

    def parse(self, response):
        items = response.css("CSS_SELECTOR")   

        for item in items:
            yield {
                "field_1": item.css("::text").get(), 
            }

        next_page = response.css("NEXT_PAGE_SELECTOR::attr(href)").get()
        if next_page:
            yield response.follow(next_page, callback=self.parse)


# This are the data point we need to scrape. 

# listingUrl   (the link to the property)
# displayAddress (full address)
# price (numeric, only fill in case the property is for sale, if it’s to let (rent) leave it blank. In case a range is provided, return the minimum price).
# propertySubType (office/retail etc)
# propertyImage (list of image urls, i.e. list of strings that would look like a python array of strings i.e in format '[‘url1’, ‘url2’, ‘url3’, etc]')
# detailedDescription (full description of the property)
# sizeFt (size of property in sq ft, numeric)
# sizeAc (size of property in acres, numeric)
# postalCode (UK postcode of property)
# brochureUrl (link to pdf brochure, just a string)
# agentCompanyName (name of the agent company, for example in this case it is LSH)
# agentName (name of marketing agent, a person, if not provided, leave blank)
# agentCity
# agentEmail
# agentPhone
# agentStreet
# agentPostcode
# tenure (one of Freehold/Leasehold)
# saleType (one of For Sale/To Let), if it is said that its both for sale and to let, then return For Sale.