import pdfplumber
import re
import json

def extract_master_metadata(pdf):
    output = {}
    def extract_text_lines(pdf, start_page=0, end_page=3):
        text = ""
        for page in pdf.pages[start_page:end_page]:
            t = page.extract_text()
            if t:
                text += t + "\n"
        return text

    # Use the pdf object passed to the function directly
    text = extract_text_lines(pdf)
    lines = text.splitlines()

    # 1. ORDER NO + DATE (detect ORDER above, NO below, date further below)
    for i, line in enumerate(lines):
        if re.search(r'\bORDER\b', line.upper()):
            if i + 1 < len(lines) and re.search(r'\bNO\b', lines[i + 1].upper()):
                order_no_match = re.search(r'\bNO[:\s]*([A-Z0-9/]+)', lines[i + 1], re.IGNORECASE)
                if order_no_match:
                    output["Order No"] = order_no_match.group(1).strip()
                if i + 2 < len(lines):
                    date_match = re.search(r'\b(\d{1,2}\.\d{1,2}\.\d{2,4})\b', lines[i + 2])
                    if date_match:
                        output["Date"] = date_match.group(1)
                break

    # 2. SOK Consumer Goods block (from page 1, capture multiple lines until next heading, exclude date)
    sok_block = []
    sok_found = False
    for i, line in enumerate(lines):
        if "SOK Consumer Goods" in line:
            sok_found = True
            # Remove "No: 163513 Page 1 (6)" and date pattern, add the base line
            cleaned_line = re.sub(r'No:\s*\d+\s*Page\s*\d+\s*\(\d+\)|(\b\d{1,2}\.\d{1,2}\.\d{2,4}\b)', '', line).strip()
            if cleaned_line:
                sok_block.append(cleaned_line)
        elif sok_found and line.strip():
            # Continue capturing lines until a new heading or empty line, exclude date
            if re.match(r'^[A-Z][A-Z ]+:', line) or not line.strip():
                break
            cleaned_line = re.sub(r'\b\d{1,2}\.\d{1,2}\.\d{2,4}\b', '', line).strip()
            if cleaned_line:
                sok_block.append(cleaned_line)
    if sok_found and sok_block:
        output["SOK Consumer Goods"] = " ".join(sok_block)
    else:
        print("⚠️ No SOK block found on page 1.")

    # 3. SUPPLIER block
    supplier_block = ""
    in_supplier = False
    for line in lines:
        if "SUPPLIER" in line.upper():
            in_supplier = True
        elif in_supplier and re.match(r'^[A-Z][A-Z ]+:', line):  # New heading
            break
        elif in_supplier:
            supplier_block += line.strip() + " "
    if supplier_block.strip():
        output["Supplier"] = supplier_block.strip().replace("SUPPLIER:", "").strip()

    # 4. Contact Person
    for line in lines:
        if "CONTACT PERSON" in line.upper():
            val = line.split(":")[-1].strip()
            if val:
                output["Contact Person"] = val
            break

    # 5–10. Delivery info
    fields = {
        "TIME OF DELIVERY": "Time of Delivery",
        "TERMS OF DELIVERY": "Delivery Terms",
        "TRANSPORT BY": "Transport By",
        "LOADING PLACE": "Loading Place",
        "DESTINATION": "Destination",
        "TERMS OF PAYMENT": "Terms of Payment",
    }
    for i, line in enumerate(lines):
        for k, v in fields.items():
            if k in line.upper():
                payment_lines = []
                payment_found = True
                for j in range(i + 1, len(lines)):
                    if re.match(r'^[A-Z][A-Z ]+:', lines[j]) or not lines[j].strip():
                        break
                    payment_lines.append(lines[j].strip())
                val = line.split(":")[-1].strip()
                if val or payment_lines:
                    output[v] = " ".join([val] + payment_lines)

    # 11–12. Order & Delivery Confirmation
    for line in lines:
        if "ORDER CONFIRMATION" in line.upper():
            val = line.split(":")[-1].strip()
            if val:
                output["Order Confirmation"] = val
        elif "DELIVERY CONFIRMATION" in line.upper():
            val = line.split(":")[-1].strip()
            if val:
                output["Delivery Confirmation"] = val

    # 13. Value of Order (can be 2 lines)
    value_lines = []
    for line in lines:
        if "VALUE OF ORDER" in line.upper():
            value_lines.append(line.strip())
            continue
        if value_lines and len(value_lines) < 2:
            value_lines.append(line.strip())
            break
    if value_lines:
        output["Value of Order"] = " ".join(value_lines)

    # 14. SUPPLY PLANNER block (until line contains a word starting with 'V' + digits)
    planner_lines = []
    in_planner = False
    for line in lines:
        if "SUPPLY PLANNER" in line.upper():
            in_planner = True
            planner_lines.append(line.strip())  # Include header
        elif in_planner:
            words = line.strip().split()
            if any(word.startswith("V") and word[1:].isdigit() for word in words):
                planner_lines.append(line.strip())  # Include Vxx line
                break
            planner_lines.append(line.strip())
    if planner_lines:
        output["Supply Planner"] = " ".join(planner_lines).strip()
    
    return output