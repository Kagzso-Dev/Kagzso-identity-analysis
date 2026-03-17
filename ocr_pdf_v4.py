import fitz
import pytesseract
import os
from PIL import Image
import io

pytesseract.pytesseract.tesseract_cmd = "C:/Program Files/Tesseract-OCR/tesseract.exe"

def ocr_pdf_pages(path):
    print(f"--- OPENING {path} ---")
    doc = fitz.open(path)
    for i in range(len(doc)):
        page = doc[i]
        pix = page.get_pixmap()
        img = Image.open(io.BytesIO(pix.tobytes()))
        txt = pytesseract.image_to_string(img)
        print(f"--- PAGE {i+1} ---")
        if txt.strip():
            print(txt)
        else:
            print("[NO TEXT]")

if __name__ == "__main__":
    folder = "C:/Users/Admin/Downloads"
    files = [f for f in os.listdir(folder) if f.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg'))]
    for f in files:
        p = os.path.join(folder, f)
        if f.lower().endswith('.pdf'):
            ocr_pdf_pages(p)
        else:
            print(f"--- IMAGE {f} ---")
            print(pytesseract.image_to_string(Image.open(p)))
