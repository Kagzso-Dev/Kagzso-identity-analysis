import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def get_ocr_text(image_path):
    try:
        text = pytesseract.image_to_string(Image.open(image_path))
        return text
    except Exception as e:
        return str(e)

if __name__ == "__main__":
    print(get_ocr_text(r"C:\Users\Admin\Downloads\bill2.jpeg"))
