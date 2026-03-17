import pytesseract
import os
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def scan_file(path):
    print(f"\n--- SCANNING: {path} ---")
    try:
        if path.lower().endswith(('.png', '.jpg', '.jpeg')):
            text = pytesseract.image_to_string(Image.open(path))
            print(text if text.strip() else "[NO TEXT FOUND]")
        else:
            print("[UNSUPPORTED FORMAT]")
    except Exception as e:
        print(f"[ERROR]: {e}")

if __name__ == "__main__":
    folder = r"C:\Users\Admin\Downloads"
    files = ["2nd.jpg", "3rd.jpg", "bill2.jpeg", "akka.jpeg", "roj.jpg", "rishu.jpg"]
    for f in files:
        scan_file(os.path.join(folder, f))
