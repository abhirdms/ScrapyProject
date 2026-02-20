import re
from urllib.parse import urljoin

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from lxml import html


class PotterAssociatesScraper:
    BASE_URL = "https://www.potterassociates.co.uk/search-results/?department=commercial"
    DOMAIN = "https://www.potterassociates.co.uk"

    def __init__(self):
        self.results = []
        self.seen_urls = set()

        chrome_options = Options()
        chrome_options.binary_location = "/usr/bin/chromium-browser"
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")

        service = Service("/usr/bin/chromedriver")
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.wait = WebDriverWait(self.driver, 20)


    def run(self):
        page = 1

        while True:
            if page == 1:
                url = self.BASE_URL
            else:
                url = f"{self.DOMAIN}/search-results/page/{page}/?department=commercial"

            self.driver.get(url)

            try:
                self.wait.until(EC.presence_of_element_located((
                    By.XPATH,
                    "//ul[contains(@class,'properties')]/li"
                )))
            except:
                break

            tree = html.fromstring(self.driver.page_source)
            listings = tree.xpath("//ul[contains(@class,'properties')]/li")

            if not listings:
                break

            new_links_found = False

            for li in listings:
                rel = li.xpath(".//h3/a/@href")
                if not rel:
                    continue

                listing_url = urljoin(self.DOMAIN, rel[0])

                if listing_url in self.seen_urls:
                    continue

                self.seen_urls.add(listing_url)
                new_links_found = True

                # -------- SIZE FROM LISTING PAGE --------
                floor_area_text = " ".join(
                    li.xpath(".//div[contains(@class,'floor-area')]//text()")
                )

                size_ft, size_ac = self.extract_size_from_listing(floor_area_text)

                try:
                    data = self.parse_listing(listing_url, size_ft, size_ac)
                    if data:
                        self.results.append(data)
                except:
                    continue

            if not new_links_found:
                break

            page += 1

        self.driver.quit()
        return self.results

  

    def parse_listing(self, url, size_ft="", size_ac=""):
        self.driver.get(url)

        self.wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//h1[contains(@class,'elementor-heading-title')]"
        )))

        tree = html.fromstring(self.driver.page_source)

        # ---------------- ADDRESS ----------------
        display_address = self.clean(" ".join(
            tree.xpath("//h1[contains(@class,'elementor-heading-title')]/text()")
        ))

        # ---------------- DESCRIPTION (NO FEATURES) ----------------
        summary_text = " ".join(
            tree.xpath("//div[contains(@class,'summary-contents')]//text()[normalize-space()]")
        )

        full_details_text = " ".join(
            tree.xpath("//div[contains(@class,'description-contents')]//text()[normalize-space()]")
        )

        combined_text = summary_text + " " + full_details_text
        combined_text = self.remove_parking_ratios(combined_text)
        detailed_description = self.clean(combined_text)

        # ---------------- PRICE ----------------
        raw_price = self.clean(" ".join(
            tree.xpath("//span[contains(@class,'commercial-rent')]/text()")
        ))

        sale_type = self.normalize_sale_type(raw_price + " " + detailed_description)
        price = self.extract_numeric_price(raw_price, sale_type)

        # ---------------- IMAGES ----------------
        property_images = list(set([
            urljoin(self.DOMAIN, img)
            for img in tree.xpath(
                "//div[contains(@class,'ph-elementor-gallery')]//a[@data-fancybox='elementor-gallery']/@href"
            )
        ]))

        # ---------------- BROCHURE ----------------
        brochure_urls = list(set([
            urljoin(self.DOMAIN, b)
            for b in tree.xpath("//li[contains(@class,'action-brochure')]//a/@href")
        ]))

        if not brochure_urls:
            brochure_urls = list(set([
                urljoin(self.DOMAIN, b)
                for b in tree.xpath("//a[contains(@href,'.pdf')]/@href")
            ]))

        # ---------------- AGENT ----------------
        agent_name = self.extract_agent_name(detailed_description)
        agent_email = self.extract_email(detailed_description)
        agent_phone = self.extract_phone(detailed_description)

        # ---------------- RETURN FULL OBJECT ----------------
        obj = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": "",
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Potter Associates",
            "agentName": agent_name,
            "agentCity": "",
            "agentEmail": agent_email,
            "agentPhone": agent_phone,
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": self.extract_tenure(detailed_description),
            "saleType": sale_type,
        }



        return obj



    def extract_size_from_listing(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "").strip()

        m = re.search(r'(\d+(?:\.\d+)?)\s*sq\.?\s*ft\b', text)
        if m:
            return float(m.group(1)), ""

        m = re.search(r'(\d+(?:\.\d+)?)\s*(acres?|acre|ac\.?)\b', text)
        if m:
            return "", float(m.group(1))

        m = re.search(r'(\d+(?:\.\d+)?)\s*(hectares?|ha)\b', text)
        if m:
            return "", round(float(m.group(1)) * 2.47105, 3)

        return "", ""



    def remove_parking_ratios(self, text):
        text = re.sub(r'underground\s+parking.*?sq\s*ft\.?', '', text, flags=re.I)
        text = re.sub(r'parking\s+at\s+a\s+ratio.*?sq\s*ft\.?', '', text, flags=re.I)
        text = re.sub(r'1\s*space\s*per\s*\d+\s*sq\s*ft\.?', '', text, flags=re.I)
        return text

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale":
            return ""

        if not text:
            return ""

        t = text.lower()

        if any(k in t for k in ["poa", "price on application"]):
            return ""

        if any(k in t for k in ["per annum", "pa", "pcm", "rent"]):
            return ""

        m = re.search(r'[£€]\s*(\d+(?:,\d{3})*(?:\.\d+)?)', t)
        if not m:
            return ""

        return str(int(float(m.group(1).replace(",", ""))))

    def normalize_sale_type(self, text):
        t = text.lower()
        if "sale" in t:
            return "For Sale"
        if "rent" in t or "to let" in t:
            return "To Let"
        return ""

    def extract_tenure(self, text):
        t = text.lower()
        if "freehold" in t:
            return "Freehold"
        if "leasehold" in t:
            return "Leasehold"
        return ""

    def extract_postcode(self, text):
        FULL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        PARTIAL = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'
        t = text.upper()
        m = re.search(FULL, t) or re.search(PARTIAL, t)
        return m.group() if m else ""

    def extract_email(self, text):
        m = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text or "")
        return m.group(0) if m else ""

    def extract_phone(self, text):
        m = re.search(r'(\+?\d[\d\s]{8,})', text or "")
        return m.group(1).strip() if m else ""

    def extract_agent_name(self, text):
        m = re.search(r'Mark\s+Potter', text, re.I)
        return m.group(0) if m else ""

    def clean(self, val):
        return " ".join(val.split()) if val else ""