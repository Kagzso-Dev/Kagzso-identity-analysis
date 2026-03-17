import fitz
import pytesseract
from PIL import Image
import io

pytesseract.pytesseract.tesseract_cmd = "C:/Program Files/Tesseract-OCR/tesseract.exe"

def scan(f):
    doc = fitz.open(f)
    print(f"--- OPENING {f} ---")
    for i, p in enumerate(doc):
        pix = p.get_pixmap()
        img = Image.open(io.BytesIO(pix.tobytes()))
        txt = pytesseract.image_to_string(img)
        print(f"--- PAGE {i+1} ---")
        print(txt)

if __name__ == "__main__":
    scan("C:/Users/Admin/Downloads/ZHT2080729.pdf")
