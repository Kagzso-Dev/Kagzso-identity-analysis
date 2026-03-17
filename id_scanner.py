import pytesseract
import os
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def scan_file(path):
    try:
        if path.lower().endswith(('.png', '.jpg', '.jpeg')):
            text = pytesseract.image_to_string(Image.open(path))
            return text
        return ""
    except:
        return ""

if __name__ == "__main__":
    folder = r"C:\Users\Admin\Downloads"
    # Scan more files
    all_files = [f for f in os.listdir(folder) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    for f in all_files:
        path = os.path.join(folder, f)
        text = scan_file(path)
        if any(kw in text.upper() for kw in ["AADHAAR", "PAN CARD", "INCOME TAX", "PASSPORT", "DRIVING LICENSE", "INVOICE", "BILL"]):
            print(f"\nMATCH FOUND in {f}:")
            print(text[:500])
