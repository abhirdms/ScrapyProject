import scrapy

class ApiSpider(scrapy.Spider):
    name = "api_spider"
    allowed_domains = ["example.com"]
    start_urls = ["https://example.com/api/items?page=1"]

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Referer": "https://example.com",
    }

    def parse(self, response):
        data = response.json()

        items = data.get("ITEMS_KEY", [])   # 🔁 CHANGE

        for item in items:
            yield {
                "field_1": item.get("key"),  # 🔁 CHANGE
            }

        next_url = data.get("NEXT_PAGE_URL")   # 🔁 CHANGE
        if next_url:
            yield scrapy.Request(
                url=next_url,
                headers=self.headers,
                callback=self.parse
            )
