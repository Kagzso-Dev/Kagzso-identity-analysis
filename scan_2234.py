import fitz
import pytesseract
from PIL import Image
import io

pytesseract.pytesseract.tesseract_cmd = "C:/Program Files/Tesseract-OCR/tesseract.exe"

def scan(p):
    doc = fitz.open(p)
    for i, page in enumerate(doc):
        pix = page.get_pixmap()
        img = Image.open(io.BytesIO(pix.tobytes()))
        txt = pytesseract.image_to_string(img)
        print(f"--- PAGE {i+1} ---")
        print(txt)

if __name__ == "__main__":
    scan("C:/Users/Admin/Downloads/2234_001.pdf")
