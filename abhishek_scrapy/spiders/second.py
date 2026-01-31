import scrapy

class HeaderHtmlSpider(scrapy.Spider):
    name = "header_html"
    allowed_domains = ["example.com"]
    start_urls = ["https://example.com"]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://google.com",
    }

    def start_requests(self):
        for url in self.start_urls:
            yield scrapy.Request(
                url,
                headers=self.headers,
                callback=self.parse
            )

    def parse(self, response):
        items = response.css("CSS_SELECTOR")   # 🔁 CHANGE

        for item in items:
            yield {
                "field_1": item.css("::text").get(),  # 🔁 CHANGE
            }

        next_page = response.css("NEXT_PAGE_SELECTOR::attr(href)").get()
        if next_page:
            yield response.follow(
                next_page,
                headers=self.headers,
                callback=self.parse
            )
