from urllib.parse import urljoin
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class HantsRealtyScraper:
    BASE_URL = "https://www.hantsrealty.co.uk/"
    DOMAIN = "https://www.hantsrealty.co.uk/"

    def __init__(self):
        self.results = []

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")

        service = Service("/usr/bin/chromedriver")

        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 30)

    # -------------------------------------------------
    # RUN
    # -------------------------------------------------

    def run(self):
        self.driver.get(self.BASE_URL)

        self.wait.until(EC.presence_of_element_located((
            By.ID, "ut-portfolio-items-45"
        )))

        # Collect post IDs once
        post_ids = self.driver.execute_script("""
            return Array.from(
                document.querySelectorAll(
                    "#ut-portfolio-items-45 article a[id^='ut-portfolio-trigger-link']"
                )
            ).map(a => a.getAttribute("data-post"));
        """)

        for post_id in post_ids:
            try:
                # Click property tile
                self.driver.execute_script("""
                    document.querySelector("a[data-post='%s']").click();
                """ % post_id)

                # Wait for modal
                self.wait.until(EC.visibility_of_element_located((
                    By.ID, f"ut-portfolio-detail-{post_id}"
                )))

                # Let animation settle
                time.sleep(0.5)

                tree = html.fromstring(self.driver.page_source)
                obj = self.parse_modal(tree, post_id)
                self.results.append(obj)

                # Close modal
                self.driver.execute_script("""
                    document.querySelector(
                        "#ut-portfolio-details-navigation-45 .close-portfolio-details"
                    ).click();
                """)

                # Allow close animation + layout reset
                time.sleep(0.5)

            except Exception:
                continue

        self.driver.quit()
        return self.results

    # -------------------------------------------------
    # PARSE MODAL
    # -------------------------------------------------

    def parse_modal(self, tree, post_id):
        modal = tree.xpath(
            f"//div[@id='ut-portfolio-detail-{post_id}']"
        )[0]

        sale_type = " ".join(
            tree.xpath(
                f"//a[@id='ut-portfolio-trigger-link-45-{post_id}']"
                "/div[contains(@class,'ut-hover-layer')]"
                "//div[@class='ut-portfolio-info-c']/span/text()"
            )
        ).strip()

        pdfs = modal.xpath(".//a[contains(@href,'.pdf')]/@href")

        brochure_urls = [
            urljoin(self.DOMAIN, u) for u in pdfs
        ]

        listing_url = (
            urljoin(self.DOMAIN, pdfs[0])
            if pdfs else ""
        )



        images = [
            urljoin(self.DOMAIN, img)
            for img in modal.xpath(
                ".//div[@class='ut-portfolio-media']//img/@src"
            )
        ]

        title = " ".join(
            modal.xpath(".//h2[@class='section-title']//span/text()")
        ).strip()

        description = " ".join(
            modal.xpath(".//div[@class='lead']//text()")
        ).strip()

        return {
            "listingUrl": listing_url,
            "displayAddress": title,

            "price": "",
            "propertySubType": "",

            "propertyImage": images,

            "detailedDescription": description,

            "sizeFt": "",
            "sizeAc": "",

            "postalCode": "",

            "brochureUrl": brochure_urls,

            "agentCompanyName": "Hants Realty",
            "agentName": "",
            "agentCity": "",
            "agentEmail": "",
            "agentPhone": "",
            "agentStreet": "",
            "agentPostcode": "",

            "tenure": "",

            "saleType": sale_type,
        }
