import pdfplumber
import re
import json


STOPWORDS = ["HOUSE", "ANTI WIND", "ADULT", "AUTO OPEN", "WIND", "AUTO-OPEN", "OPEN"]

def extract_blocks(text):
    pattern = r'(^\d+\).*?)(?=^\d+\)|^Suomen Osuuskauppojen Keskuskunta|\Z)'
    blocks = re.findall(pattern, text, re.MULTILINE | re.DOTALL)

    # Check and merge "ARTICLE GENERAL INFORMATION"
    general_info_match = re.search(r'(ARTICLE GENERAL INFORMATION.*)', text, re.IGNORECASE | re.DOTALL)
    if general_info_match:
        general_info = general_info_match.group(1).strip()
        if blocks:
            blocks[-1] = blocks[-1].strip() + "\n" + general_info
        else:
            blocks.append(general_info)

    return blocks

def extract_article_line(block, style=None):
    for line in block.split("\n"):
        line_upper = line.upper()
        if style and style in line:
            end_indices = []
            for kw in STOPWORDS:
                kw_index = line_upper.find(kw.upper())
                if kw_index != -1:
                    end_indices.append(kw_index + len(kw))
            style_index = line.find(style)
            if style_index != -1:
                end_indices.append(style_index + len(style))
            if end_indices:
                cutoff = max(end_indices)
                return line[:cutoff].strip()
            return line.strip()

        for kw in STOPWORDS:
            if kw.upper() in line_upper:
                end = line_upper.find(kw.upper()) + len(kw)
                return line[:end].strip()
    return None

def parse_block(block):
    data = {}

    # === Style ===
    style_match = re.search(r'STYLE\s*[:\-]?\s*([A-Z0-9\-]{6,})', block, re.IGNORECASE)
    if style_match:
        data["Style"] = style_match.group(1).strip()

    # === Article ===
    article = extract_article_line(block, data.get("Style"))
    if article:
        data["Article"] = article

    # === Quantity and Unit ===
    qty_match = re.search(r'\b([\d.,]+)\s+(PC)\b', block)
    if qty_match:
        data["Quantity"] = qty_match.group(1).strip()
        data["Unit"] = qty_match.group(2).strip()

    # === Price ===
    price_match = re.search(r'([\d.,]+)\s+USD\b', block)
    if price_match:
        data["Price/Unit Gross"] = price_match.group(1).strip() + " USD"

    # === Info (Exclude PREHANDLING/PARCEL) ===
    info_match = re.search(
        r'(?<!PREHANDLING\s)(?<!PARCEL LABEL CODE\s)INFO:\s*(.*?)(?=\s+[A-Z ]+:\s*|$)',
        block,
        re.DOTALL | re.IGNORECASE
    )
    if info_match:
        info_clean = re.sub(r'\s+', ' ', info_match.group(1)).strip()
        info_clean = re.sub(r'Style\s*:\s*[A-Z0-9\-]+', '', info_clean, flags=re.IGNORECASE).strip()
        if info_clean:
            data["Info"] = info_clean

    # === Flatten block for simplified matching ===
    flat = re.sub(r'\s+', ' ', block)

    # === EAN Code ===
    if m := re.search(r'\b(\d{13})\b', flat):
        data["EAN Code"] = m.group(1)

    # === Article Number ===
    if m := re.search(r'\b(\d{8}|\d{11})\b(?!\d)', flat):  # Avoid 13-digit EAN
        data["Art No"] = m.group(1)

    # === Supp. Art. No === (updated logic to include SOK__2_tt03ppkkvv)
    if m := re.search(r'\b(KTAW[A-Z0-9\-_]+|KT[A-Z0-9\-_]+|[A-Z]{2,}__\d+_[a-z0-9_]+)\b', flat, re.IGNORECASE):
        data["Supp. Art. No"] = m.group(1)

    # === Colour (hybrid logic) ===
    colour_match = re.search(r'COLOUR:\s*', flat, re.IGNORECASE)
    if colour_match:
        start_idx = colour_match.end()
        remaining = flat[start_idx:]
        stop_keywords = ["SIZE:", "SALES LOT", "BRAND:", "COUNTRY OF ORIGIN:", "CUSTOMS TARIFF", "PREHANDLING", "PARCEL LABEL"]
        stop_idx = len(remaining)
        for kw in stop_keywords:
            i = remaining.upper().find(kw)
            if i != -1 and i < stop_idx:
                stop_idx = i
        colour_value = remaining[:stop_idx].strip()
        if colour_value:
            data["Colour"] = colour_value

    # === Size fix ===
    if m := re.search(r'SIZE:\s*([A-Z0-9\- ]+?)(?:\s+SALES LOT SL|$)', flat):
        data["Size"] = m.group(1).strip()

    # === Remaining keys ===
    if m := re.search(r'SALES LOT SL:\s*(\d+\s*PC)', flat):
        data["Sales Lot"] = m.group(1)
    if m := re.search(r'BRAND:\s*(\S+)', flat):
        data["Brand"] = m.group(1)
    if m := re.search(r'COUNTRY OF ORIGIN:\s*(\S+)', flat):
        data["Country of Origin"] = m.group(1)
    if m := re.search(r'CUSTOMS TARIFF NUMBER:\s*(\d+)', flat):
        data["Customs Tariff Number"] = m.group(1)
    if m := re.search(r'PREHANDLING INFO:\s*(PREHANDLING INCLUDED)', flat):
        data["Prehandling Info"] = m.group(1)
    if m := re.search(r'PARCEL LABEL CODE:\s*(\S+)', flat):
        data["Parcel Label Code"] = m.group(1)

    return data

# === Main Flow ===
def parse_pdf_without_heading(pdf_path):
    parsed_items = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page_num in range(2, 6):  # Pages 3–6 (0-indexed)
                if page_num < len(pdf.pages):
                    page_text = pdf.pages[page_num].extract_text(x_tolerance=2)
                    if page_text:
                        full_text += page_text + "\n"

            blocks = extract_blocks(full_text)
            print(f"🔍 Found {len(blocks)} item blocks")
            for block in blocks:
                result = parse_block(block)
                if result:
                    parsed_items.append(result)

    except Exception as e:
        print("❌ Error:", e)

    if parsed_items:
        with open("combined.json", "w", encoding="utf-8") as f:
            json.dump(parsed_items, f, indent=4, ensure_ascii=False)
        print("✅ Saved to partone.json")
    else:
        print("⚠️ No items parsed.")

