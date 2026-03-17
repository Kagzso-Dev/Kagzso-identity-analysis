import pytesseract
import os
import re
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = "C:/Program Files/Tesseract-OCR/tesseract.exe"

def scan_for_ids(path):
    fn = os.path.basename(path)
    print(f"\n--- SCANNING: {fn} ---")
    try:
        if path.lower().endswith(('.png', '.jpg', '.jpeg')):
            text = pytesseract.image_to_string(Image.open(path))
        else:
            return

        # PAN regex
        pan = re.search(r'[A-Z]{5}[0-9]{4}[A-Z]', text.upper())
        # Aadhaar regex - 12 digits (with potential spaces)
        aadhaar = re.search(r'\d{4}\s?\d{4}\s?\d{4}', text)
        # Passport - usually starts with a letter and 7 digits
        passport = re.search(r'[A-Z][0-9]{7}', text.upper())
        
        if pan: print(f"PAN FOUND: {pan.group()}")
        if aadhaar: print(f"AADHAAR FOUND: {aadhaar.group()}")
        if passport: print(f"PASSPORT FOUND: {passport.group()}")
        
        if not (pan or aadhaar or passport):
             print(f"NO IDS FOUND. TEXT PREVIEW: {text.strip().replace('\\n', ' ')[:200]}...")

    except Exception as e:
        print(f"[ERROR]: {e}")

if __name__ == "__main__":
    folder = "C:/Users/Admin/Downloads"
    # Also check if there's any ID-like files I missed
    files = ["akka.jpeg", "roj.jpg", "rishu.jpg", "bill2.jpeg", "2nd.jpg", "3rd.jpg"]
    # ... List all images ...
    imgs = [f for f in os.listdir(folder) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
    for f in imgs:
        scan_for_ids(os.path.join(folder, f))
