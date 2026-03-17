"""
Kagzso – Desktop OCR Pipeline
Scan image/PDF → OCR → Send to Kagzso backend → Print structured result
"""

import os
import io
import sys
import json
import requests
import pytesseract
import fitz  # PyMuPDF
from PIL import Image

# ─── Config ───────────────────────────────────────────────────────────────────
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
BACKEND_URL = "http://localhost:8000/scan"

SUPPORTED_IMAGES = ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp')
SUPPORTED_PDF    = ('.pdf',)

# ─── OCR Functions ────────────────────────────────────────────────────────────
def ocr_image(path: str) -> str:
    img = Image.open(path)
    return pytesseract.image_to_string(img)


def ocr_pdf(path: str) -> str:
    """Render all PDF pages to image and OCR each one."""
    doc = fitz.open(path)
    full_text = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=200)
        img = Image.open(io.BytesIO(pix.tobytes("jpeg")))
        text = pytesseract.image_to_string(img)
        if text.strip():
            full_text.append(f"[Page {i+1}]\n{text}")
    doc.close()
    return "\n".join(full_text)


def extract_text(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext in SUPPORTED_IMAGES:
        return ocr_image(path)
    elif ext in SUPPORTED_PDF:
        return ocr_pdf(path)
    else:
        raise ValueError(f"Unsupported file type: {ext}")

# ─── Backend Call ─────────────────────────────────────────────────────────────
def send_to_kagzso(file_path: str) -> dict:
    with open(file_path, 'rb') as f:
        resp = requests.post(
            BACKEND_URL,
            files={"file": f},
            timeout=60
        )
    resp.raise_for_status()
    return resp.json()

# ─── Pretty Print Result ──────────────────────────────────────────────────────
def print_result(filename: str, result: dict):
    sep = "─" * 50
    print(f"\n{sep}")
    print(f"  FILE : {filename}")
    print(f"  TYPE : {result.get('document_type', 'Unknown')}")
    print(sep)

    field_labels = {
        "name":          "Name",
        "dob":           "Date of Birth",
        "id_number":     "ID Number",
        "father_name":   "Father's Name",
        "address":       "Address",
        "issue_date":    "Issue Date",
        "expiry_date":   "Expiry Date",
    }

    found_any = False
    for key, label in field_labels.items():
        value = result.get(key)
        if value:
            print(f"  {label:<15}: {value}")
            found_any = True

    if not found_any:
        print("  [No fields extracted]")

    print(sep)

# ─── Scan Single File ─────────────────────────────────────────────────────────
def process_file(path: str):
    filename = os.path.basename(path)
    print(f"\n→ Scanning: {filename}")

    try:
        raw_text = extract_text(path)
    except Exception as e:
        print(f"  [OCR ERROR] {e}")
        return

    if not raw_text.strip():
        print("  [NO TEXT DETECTED] Try a clearer image.")
        return

    print(f"  Sending to Kagzso...")

    try:
        result = send_to_kagzso(path)
        print_result(filename, result)
    except requests.exceptions.ConnectionError:
        print("  [BACKEND ERROR] Cannot connect. Is the server running?")
        print(f"  Start it: python app.py")
    except requests.exceptions.HTTPError as e:
        print(f"  [BACKEND ERROR] {e}")
    except Exception as e:
        print(f"  [ERROR] {e}")

# ─── Scan Folder ──────────────────────────────────────────────────────────────
def process_folder(folder: str):
    all_exts = SUPPORTED_IMAGES + SUPPORTED_PDF
    files = [
        os.path.join(folder, f)
        for f in sorted(os.listdir(folder))
        if os.path.splitext(f)[1].lower() in all_exts
    ]

    if not files:
        print(f"No supported files found in: {folder}")
        return

    print(f"\nKagzso OCR Pipeline – {len(files)} file(s) found in {folder}")
    for path in files:
        process_file(path)

# ─── Entry Point ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Single file or folder passed as argument
        target = sys.argv[1]
        if os.path.isdir(target):
            process_folder(target)
        elif os.path.isfile(target):
            process_file(target)
        else:
            print(f"Path not found: {target}")
    else:
        # Default: scan Downloads folder
        folder = r"C:\Users\Admin\Downloads"
        process_folder(folder)
