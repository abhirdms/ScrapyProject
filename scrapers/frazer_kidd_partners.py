import re
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from lxml import html


class FrazerKiddPartnersScraper:
    BASE_URL = "https://www.frazerkidd.co.uk/Property?Term=&PropertyTypeID=0&search=SEARCH&AreaID=0&Price=999999999"
    DOMAIN = "https://www.frazerkidd.co.uk"

    def __init__(self):
        self.results = []
        self.seen_urls = set()
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                )
            }
        )

    # ===================== RUN ===================== #

    def run(self):
        page = 1

        while True:
            if page == 1:
                page_url = self.BASE_URL
            else:
                page_url = (
                    f"{self.DOMAIN}/Property?page={page}"
                    "&propertytypeid=0&areaid=0&price=999999999"
                )

            tree = self.get_tree(page_url)
            if tree is None:
                break

            listing_cards = tree.xpath("//div[contains(@class,'list') and contains(@class,'w-row')]")
            if not listing_cards:
                break

            new_urls_on_page = 0

            for card in listing_cards:

                status_text = self._clean(" ".join(card.xpath(".//div[contains(@class,'stats-status')]/text()")))
                if self.is_sold(status_text):
                    continue

                href_list = card.xpath(".//a[contains(@href,'/Property/Details/')]/@href")
                if not href_list:
                    continue

                raw_url = urljoin(self.DOMAIN, href_list[0])

                # Remove query parameters (clean canonical URL)
                parsed = urlparse(raw_url)
                listing_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))

                if listing_url in self.seen_urls:
                    continue

                self.seen_urls.add(listing_url)
                new_urls_on_page += 1

                try:
                    row = self.parse_listing(listing_url, card)
                    if row:
                        self.results.append(row)
                except Exception:
                    continue

            if new_urls_on_page == 0:
                break

            page += 1

        return self.results

    # ===================== LISTING ===================== #

    def parse_listing(self, url, card=None):
        tree = self.get_tree(url)
        if tree is None:
            return None

        card = card or html.fromstring("<div></div>")

        # ---------------- ADDRESS ---------------- #

        display_address = self._clean(" ".join(
            tree.xpath("//div[contains(@class,'detail-left')]//h3[contains(@class,'bold-h3')][1]//text()")
        ))

        if not display_address:
            display_address = self._clean(" ".join(
                tree.xpath("//h2[contains(@class,'list-heading')][1]/text()")
            ))

        if not display_address:
            display_address = self._clean(" ".join(
                card.xpath(".//h3[contains(@class,'list-address')]/text()")
            ))

        # ---------------- SALE TYPE ---------------- #

        sale_type_raw = self._clean(" ".join(
            tree.xpath(
                "//div[contains(@class,'right-stats-status')][1]/text()"
                " | //div[contains(@class,'rights-stats')]//div[contains(@class,'right-stats-status')][1]/text()"
            )
        ))

        if not sale_type_raw:
            sale_type_raw = self._clean(" ".join(card.xpath(".//div[contains(@class,'stats-status')]/text()")))

        if self.is_sold(sale_type_raw):
            return None

        sale_type = self.normalize_sale_type(sale_type_raw)

        # ---------------- PROPERTY TYPE ---------------- #

        subtype_nodes = tree.xpath("//div[contains(@class,'right-stats-type')][1]/text()")
        if not subtype_nodes:
            subtype_nodes = card.xpath(".//div[contains(@class,'stats-type')]/text()")

        property_sub_type = self._clean(" ".join(list(dict.fromkeys(
            [self._clean(x) for x in subtype_nodes if self._clean(x)]
        ))))

        # ---------------- PRICE ---------------- #

        price_text = self._clean(" ".join(
            tree.xpath(
                "//h3[contains(@class,'price')]//text()"
                " | //div[contains(@class,'right-price')]//h3//text()"
            )
        ))

        if not price_text:
            price_text = self._clean(" ".join(card.xpath(".//div[contains(@class,'stas-price')]//text()")))

        price = self.extract_numeric_price(price_text, sale_type)

        # ---------------- DESCRIPTION ---------------- #

        detail_paragraphs = [
            self._clean(t)
            for t in tree.xpath("//p[contains(@class,'left')]/text()")
            if self._clean(t)
        ]

        key_features = [
            self._clean(t)
            for t in tree.xpath("//h2[contains(normalize-space(),'Key features')]/following-sibling::ul[1]/li/text()")
            if self._clean(t)
        ]

        listing_desc = self._clean(" ".join(card.xpath(".//p[contains(@class,'list-description')]//text()")))

        description_parts = list(dict.fromkeys(
            [listing_desc, *detail_paragraphs, *key_features]
        ))

        detailed_description = self._clean(" ".join([x for x in description_parts if x]))

        # ---------------- SIZE ---------------- #

        size_text = self._clean(" ".join(
            tree.xpath("//p[contains(@class,'right-size')]//text()")
        ))

        size_ft, size_ac = self.extract_size(" ".join([size_text, detailed_description]))

        # ---------------- IMAGES ---------------- #

        property_images = []
        for src in tree.xpath(
            "//ul[@id='lightSlider']/li/@data-src"
            " | //ul[contains(@class,'lSPager')]//img/@src"
        ):
            abs_src = urljoin(self.DOMAIN, src)
            if abs_src and abs_src not in property_images:
                property_images.append(abs_src)

        # ---------------- BROCHURE ---------------- #

        brochure_urls = []
        for href in tree.xpath(
            "//h3[normalize-space()='Downloads']/following-sibling::div//a/@href"
            " | //a[contains(@href,'.pdf')]/@href"
        ):
            abs_href = urljoin(self.DOMAIN, href)
            if abs_href and abs_href not in brochure_urls:
                brochure_urls.append(abs_href)

        # ---------------- AGENT ---------------- #

        agent_name = ""
        agent_phone = ""
        agent_email = ""

        enquire_text = self._clean(" ".join(
            tree.xpath("//h3[normalize-space()='Enquire']/following-sibling::div[1]//p//text()")
        ))

        if enquire_text:
            name_match = re.search(r"name\s*:\s*([^\n\r]+?)(?=telephone\s*:|mobile\s*:|$)", enquire_text, re.I)
            if name_match:
                agent_name = self._clean(name_match.group(1))

            tel_match = re.search(r"(telephone|mobile)\s*:\s*(\+?\d[\d\s().-]{7,}\d)", enquire_text, re.I)
            if tel_match:
                agent_phone = self._clean(tel_match.group(2))

        mailto = self._clean(" ".join(
            tree.xpath("//h3[normalize-space()='Enquire']/following-sibling::div[1]//a[starts-with(@href,'mailto:')]/@href")
        ))
        if mailto:
            agent_email = mailto.replace("mailto:", "").strip()

        # ---------------- BUILD ROW ---------------- #

        row = {
            "listingUrl": url,
            "displayAddress": display_address,
            "price": price,
            "propertySubType": property_sub_type,
            "propertyImage": property_images,
            "detailedDescription": detailed_description,
            "sizeFt": size_ft,
            "sizeAc": size_ac,
            "postalCode": self.extract_postcode(display_address),
            "brochureUrl": brochure_urls,
            "agentCompanyName": "Frazer Kidd Partners",
            "agentName": agent_name,
            "agentCity": "",
            "agentEmail": agent_email,
            "agentPhone": agent_phone,
            "agentStreet": "",
            "agentPostcode": "",
            "tenure": self.extract_tenure(detailed_description),
            "saleType": sale_type,
        }


        return row

    # ===================== HELPERS ===================== #

    def get_tree(self, url):
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return html.fromstring(response.text)
        except Exception:
            return None

    def extract_size(self, text):
        if not text:
            return "", ""

        text = text.lower().replace(",", "")
        text = text.replace("ft²", "sq ft").replace("m²", "sqm")
        text = re.sub(r"[–—−]", "-", text)

        size_ft = ""
        size_ac = ""

        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\.?\s*ft|sqft|sf)", text)
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ft = round(min(a, b), 3) if b else round(a, 3)

        m = re.search(r"(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac\.?)", text)
        if m:
            a = float(m.group(1))
            b = float(m.group(2)) if m.group(2) else None
            size_ac = round(min(a, b), 3) if b else round(a, 3)

        return size_ft, size_ac

    def extract_numeric_price(self, text, sale_type):
        if sale_type != "For Sale" or not text:
            return ""

        t = text.lower()

        if any(k in t for k in ["poa", "price on application", "upon application"]):
            return ""

        if any(k in t for k in ["per annum", "pa", "pcm", "rent"]):
            return ""

        m = re.search(r"[£€]?\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*m?", t)
        if not m:
            return ""

        num = float(m.group(1).replace(",", ""))
        if "m" in m.group(0):
            num *= 1_000_000

        return str(int(num))

    def extract_tenure(self, text):
        t = (text or "").lower()
        if "freehold" in t:
            return "Freehold"
        if "leasehold" in t:
            return "Leasehold"
        return ""

    def extract_postcode(self, text: str):
        if not text:
            return ""

        text = text.upper()

        full_pattern = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}\b'
        partial_pattern = r'\b[A-Z]{1,2}\d{1,2}[A-Z]?\b'

        match = re.search(full_pattern, text)
        if match:
            return match.group().strip()

        match = re.search(partial_pattern, text)
        return match.group().strip() if match else ""

    def normalize_sale_type(self, text):
        t = (text or "").lower()
        if "sold" in t:
            return "Sold"
        if "sale" in t:
            return "For Sale"
        if "let" in t or "rent" in t:
            return "To Let"
        return self._clean(text)

    def is_sold(self, text):
        return "sold" in (text or "").lower()

    def _clean(self, val):
        return " ".join(val.split()) if val else ""