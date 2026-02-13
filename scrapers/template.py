# size_extraction 


import re


def extract_size(text: str):

    if not text:
        return "", ""

    SQM_TO_SQFT = 10.7639
    HECTARE_TO_ACRE = 2.47105

    text = text.lower().replace(",", "")
    text = re.sub(r"[–—−]", "-", text)

    size_ft = ""
    size_ac = ""

    # ---- UPDATED SQ FT REGEX (supports sq. ft.) ----
    m = re.search(
        r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sq\.?\s*ft\.?|sqft|sf)\b',
        text
    )
    if m:
        a = float(m.group(1))
        b = float(m.group(2)) if m.group(2) else None
        size_ft = round(min(a, b), 3) if b else round(a, 3)
        return size_ft, size_ac

    m = re.search(
        r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(sqm|m2|m²)\b',
        text
    )
    if m:
        a = float(m.group(1))
        b = float(m.group(2)) if m.group(2) else None
        val = min(a, b) if b else a
        size_ft = round(val * SQM_TO_SQFT, 3)
        return size_ft, size_ac

    m = re.search(
        r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(acres?|acre|ac)\b',
        text
    )
    if m:
        a = float(m.group(1))
        b = float(m.group(2)) if m.group(2) else None
        size_ac = round(min(a, b), 3) if b else round(a, 3)
        return size_ft, size_ac

    m = re.search(
        r'(\d+(?:\.\d+)?)\s*(?:-|to)?\s*(\d+(?:\.\d+)?)?\s*(hectares?|hectare|ha)\b',
        text
    )
    if m:
        a = float(m.group(1))
        b = float(m.group(2)) if m.group(2) else None
        val = min(a, b) if b else a
        size_ac = round(val * HECTARE_TO_ACRE, 3)
        return size_ft, size_ac

    return size_ft, size_ac





################################## lease ###############################
def extract_tenure(text: str):
    if not text:
        return ""
    
    t = text.lower()

    if "freehold" in t:
        return "Freehold"

    if "leasehold" in t:
        return "Leasehold"

    return ""


################################# postcode

def extract_postcode(text: str):
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


#################################### price ##############################

def extract_price(text: str, sale_type: str = None):
    if not text:
        return ""

    if sale_type and sale_type.lower() != "for sale":
        return ""

    raw = (
        text.lower()
        .replace(",", "")
        .replace("\u00a0", " ")
    )

    raw = re.sub(r"(to|–|—)", "-", raw)

    prices = []

    # Remove rent-based segments
    rent_keywords = [
        "per annum", "pa", "pcm",
        "per calendar month", "per sq ft", "psf"
    ]
    for word in rent_keywords:
        raw = re.sub(rf"£?\s*\d+(?:\.\d+)?\s*{word}", "", raw)

    # Standard £ prices (avoid small psf values)
    for val in re.findall(r"£\s*(\d{5,})", raw):
        prices.append(float(val))

    # Million format
    million_matches = re.findall(
        r"(?:£\s*)?(\d+(?:\.\d+)?)\s*(million|m)\b",
        raw
    )
    for num, _ in million_matches:
        prices.append(float(num) * 1_000_000)

    if prices:
        price = min(prices)
        return str(int(price)) if price.is_integer() else str(price)

    # If no numeric price found and POA wording exists
    if any(x in raw for x in [
        "poa",
        "price on application",
        "upon application",
        "on application"
    ]):
        return ""

    return ""

