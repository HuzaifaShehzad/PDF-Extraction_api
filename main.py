import pdfplumber
import re
import json
from partone import parse_pdf_without_heading, parse_block, extract_blocks
from parttwo import parse_pdf_with_heading, extract_general_info_blocks, parse_general_info, extract_product_blocks, parse_product_block
from master import extract_master_metadata


def has_article_general_info(pdf_path, max_pages_to_check=5):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for i in range(min(len(pdf.pages), max_pages_to_check)):
                text = pdf.pages[i].extract_text()
                if text and "ARTICLE GENERAL INFORMATION" in text.upper():
                    return True
    except Exception as e:
        print(f"❌ Error reading PDF: {e}")
    return False


def parse_combined_pdf(pdf_path):
    final_result = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            # ✅ 1. Extract master metadata first
            master_data = extract_master_metadata(pdf)
            if master_data:
                final_result.append({"MASTER METADATA": master_data})
                print("✅ Master metadata extracted and added.")

            # ✅ 2. Read all text for layout decision
            full_text = ""
            for page_num in range(len(pdf.pages)):
                page = pdf.pages[page_num]
                text = page.extract_text(x_tolerance=3)
                if text:
                    full_text += f"\n--- Page {page_num + 1} ---\n{text}\n"

            # ✅ 3. Check if 'ARTICLE GENERAL INFORMATION' is present
            match = re.search(r'ARTICLE GENERAL INFORMATION', full_text, re.IGNORECASE)
            if match:
                before_text = full_text[:match.start()]
                after_text = full_text[match.start():]

                # ✅ 4. Handle Part One (before heading)
                pre_blocks = extract_blocks(before_text)
                print(f"🔎 Found {len(pre_blocks)} pre-heading item blocks")
                for block in pre_blocks:
                    result = parse_block(block)
                    if result:
                        final_result.append(result)

                # ✅ 5. Handle Part Two (after heading)
                general_sections = extract_general_info_blocks(after_text)
                total_qty_match = re.search(r'Total\s*(?:quantity\s*)?of\s*articles\s*:\s*(\d+\s*PC)', after_text, re.IGNORECASE)
                global_total = {"Total quantity of articles": total_qty_match.group(1).strip()} if total_qty_match else None

                for i, section in enumerate(general_sections):
                    general_info = parse_general_info(section)

                    # If total quantity is embedded inside general_info, extract it separately
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

            else:
                print("📄 No 'ARTICLE GENERAL INFORMATION' found — using Part ONE parser")
                parse_pdf_without_heading(pdf_path)
                return  # partone already saves its output separately

    except Exception as e:
        print("❌ Error while processing PDF:", e)

    # ✅ 6. Write all combined output
    if final_result:
        with open("combined.json", "w", encoding="utf-8") as f:
            json.dump(final_result, f, indent=4, ensure_ascii=False)
        print("✅ Saved full data to combined.json")
    else:
        print("⚠️ No valid data extracted.")


# ✅ This is the function your FastAPI `api.py` will call
def run_from_api(pdf_path):
    parse_combined_pdf(pdf_path)


# ✅ This block is for manual command-line testing
if __name__ == "__main__":
    pdf_path = "PO_1.pdf"  # ⬅️ change this if testing manually
    parse_combined_pdf(pdf_path)
