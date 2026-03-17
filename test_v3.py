import pytesseract
from PIL import Image
import os
import re

pytesseract.pytesseract.tesseract_cmd = "C:/Program Files/Tesseract-OCR/tesseract.exe"

def scan(f):
    if not os.path.exists(f): return
    print(f"--- {os.path.basename(f)} ---")
    txt = pytesseract.image_to_string(Image.open(f))
    print(txt)

if __name__ == "__main__":
    scan("C:/Users/Admin/Downloads/akka.jpeg")
    scan("C:/Users/Admin/Downloads/roj.jpg")
