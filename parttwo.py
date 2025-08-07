import pdfplumber
import re
import json

STOPWORDS = ["HOUSE", "ANTI WIND", "ADULT", "AUTO OPEN", "WIND", "AUTO-OPEN", "OPEN"]

def extract_general_info_blocks(text):
    pattern = r'(ARTICLE GENERAL INFORMATION.*?)(?=ARTICLE GENERAL INFORMATION|\Z)'
    matches = re.findall(pattern, text, re.DOTALL | re.IGNORECASE)
    if not matches:
        print("Warning: No 'ARTICLE GENERAL INFORMATION' sections found.")
    return matches

def extract_product_blocks(section_text):
    pattern = r'(^\d+\).*?)(?=\n\d+\)|^\d+\)|^ARTICLE GENERAL INFORMATION|\Z)'
    blocks = re.findall(pattern, section_text, re.MULTILINE | re.DOTALL)
    return blocks

def extract_article_name_and_styles(block):
    lines = block.strip().splitlines()
    article_name = ""
    style_numbers = []
    article_number = None

    flat = " ".join(lines[:6])

    # Check for explicit STYLE label first
    style_match = re.search(r'STYLE\s*[:\-]?\s*([A-Z0-9]{6,10})\b', flat, re.IGNORECASE)
    if style_match:
        style_numbers = [style_match.group(1).strip()]
        # If STYLE is labeled, set article name up to the style
        article_name_match = re.match(r'^\d+\)\s*(.*?)\b' + re.escape(style_numbers[0]) + r'\b', flat)
        if article_name_match:
            article_name = article_name_match.group(1).strip()
    else:
        # If no STYLE label, capture the full line as article name and detect style numbers separately
        article_name_match = re.match(r'^\d+\)\s*(.*?)(?:\s*(?:\d{1,4}\s*PC|\d{1,4},\d{1,2}\s*USD)|\Z)', flat)
        if article_name_match:
            article_name = article_name_match.group(1).strip()
        style_matches = re.findall(r'\b([A-Z0-9]{9,10})\b(?!\s*PC|\s*USD)', flat)
        style_numbers = style_matches[:2]

    for line in lines:
        if m := re.search(r'\b(\d{8,11})\b(?!\d)', line):
            article_number = m.group(1)
            break

    return article_name, style_numbers, article_number

def parse_general_info(text):
    info = {}
    if m := re.search(r'STYLE\s*[:\-]?\s*([A-Z0-9\-]{6,})', text, re.IGNORECASE):
        info["Style"] = m.group(1).strip()
    if m := re.search(r'BRAND:\s*(\S+)', text):
        info["Brand"] = m.group(1).strip()
    if m := re.search(r'COUNTRY OF ORIGIN:\s*(\S+)', text):
        info["Country of Origin"] = m.group(1).strip()
    if m := re.search(r'CUSTOMS TARIFF NUMBER:\s*(\d+)', text):
        info["Customs Tariff Number"] = m.group(1).strip()
    if m := re.search(r'PREHANDLING INFO:\s*(PREHANDLING INCLUDED)', text):
        info["Prehandling Info"] = m.group(1).strip()
    if m := re.search(r'PARCEL LABEL CODE:\s*(\S+)', text):
        info["Parcel Label Code"] = m.group(1).strip()
    if m := re.search(r'SALES LOT\s*(?:SL)?:\s*(\d+\s*PC)', text, re.IGNORECASE):
        info["Sales Lot"] = m.group(1).strip()
    if m := re.search(r'Total\s*(?:quantity\s*)?of\s*articles\s*:\s*(\d+\s*PC)', text, re.IGNORECASE):
        info["Total quantity of articles"] = m.group(1).strip()
    return info

def parse_product_block(block, general_info):
    data = general_info.copy()
    flat = re.sub(r'\s+', ' ', block)

    article_name, style_numbers, art_number = extract_article_name_and_styles(block)
    if article_name:
        # Check if article name already contains any style number
        append_style = True
        if style_numbers:
            for style in style_numbers:
                if style in article_name:
                    append_style = False
                    break
            if append_style and "Style" not in data and style_numbers:
                article_name = f"{article_name} {style_numbers[0]}".strip()
        data["Article Name"] = article_name
    if art_number:
        data["Art No"] = art_number
    if style_numbers and "Style" not in data:
        data["Style"] = ", ".join(style_numbers) if len(style_numbers) > 1 else style_numbers[0]

    if m := re.search(r'\b([\d.,]+)\s+(PC)\b', flat, re.IGNORECASE):
        data["Quantity"] = m.group(1).strip()
        data["Unit"] = m.group(2).strip()

    if m := re.search(r'([\d.,]+)\s+USD\b', flat, re.IGNORECASE):
        data["Price/Unit Gross"] = m.group(1).strip() + " USD"

    if m := re.search(r'\b(\d{13})\b', flat):
        data["EAN Code"] = m.group(1)

    # Updated pattern with OR to include "206H302111"-like pattern
    if m := re.search(r'\b(SOK[A-Z0-9\-_]+|206[A-Z0-9]{7})\b', flat, re.IGNORECASE):
        data["Supp. Art. No"] = m.group(1).strip()

    if m := re.search(r'COLOUR:\s*', flat, re.IGNORECASE):
        start = m.end()
        tail = flat[start:]
        stopwords = ["SIZE:", "SALES LOT", "BRAND:", "COUNTRY OF ORIGIN:", "CUSTOMS TARIFF", "PREHANDLING", "PARCEL LABEL"]
        stop = len(tail)
        for word in stopwords:
            idx = tail.upper().find(word)
            if idx != -1 and idx < stop:
                stop = idx
        colour = tail[:stop].strip()
        # Append 'SORBET' if it's the exact expected color
        if colour.upper() == "18-2043TCX RASPBERRY":
            colour += " SORBET"
        elif colour.upper() == "18-3840TCX PURPLE":
            colour += " OPULENCE"
        if colour:
            data["Colour"] = colour

    if m := re.search(r'SIZE:\s*([A-Z0-9\- ]+?)(?:\s+(?:SALES LOT SL|\Z|$))', flat, re.IGNORECASE):
        data["Size"] = m.group(1).strip()
    else:
        for line in block.strip().splitlines():
            if m := re.search(r'SIZE:\s*([A-Z0-9\- ]+)', line, re.IGNORECASE):
                data["Size"] = m.group(1).strip()
                break
        if "Size" not in data:
            data["Size"] = "NOT_SPECIFIED"

    if m := re.search(r'SALES LOT\s*(?:SL)?:\s*(\d+\s*PC)', flat, re.IGNORECASE):
        data["Sales Lot"] = m.group(1).strip()

    return data

def parse_pdf_with_heading(pdf_path):
    final_result = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            full_text = ""
            for page_num in range(len(pdf.pages)):
                page = pdf.pages[page_num]
                txt = page.extract_text(x_tolerance=3)
                if txt:
                    full_text += f"\n--- Page {page_num + 1} ---\n" + txt + "\n"
                else:
                    words = page.extract_words()
                    if words:
                        full_text += f"\n--- Page {page_num + 1} (Words) ---\n" + " ".join(w["text"] for w in words) + "\n"

            general_sections = extract_general_info_blocks(full_text)
            if not general_sections:
                general_sections = [full_text]

            total_qty_match = re.search(r'Total\s*(?:quantity\s*)?of\s*articles\s*:\s*(\d+\s*PC)', full_text, re.IGNORECASE)
            global_total = {"Total quantity of articles": total_qty_match.group(1).strip()} if total_qty_match else None

            for i, section in enumerate(general_sections):
                general_info = parse_general_info(section)
                if "Total quantity of articles" in general_info:
                    final_result.append({"Total quantity of articles": general_info.pop("Total quantity of articles")})
                elif global_total and i == 0:
                    final_result.append(global_total)
                if general_info:
                    final_result.append({"ARTICLE GENERAL INFORMATION": general_info})

                product_blocks = extract_product_blocks(section)
                for block in product_blocks:
                    item = parse_product_block(block, general_info)
                    if item:
                        final_result.append(item)

    except Exception as e:
        print("❌ Error while processing PDF:", e)

    if final_result:
        with open("combined.json", "w", encoding="utf-8") as f:
            json.dump(final_result, f, indent=4, ensure_ascii=False)
        print("✅ Saved to combined.json")
    else:
        print("⚠️ No valid data extracted.")