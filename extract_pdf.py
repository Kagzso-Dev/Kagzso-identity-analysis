import pdfplumber
import os

def extract_pdf_text(path):
    print(f"\n--- EXTRACTING PDF: {path} ---")
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                print(page.extract_text())
    except Exception as e:
        print(f"[ERROR]: {e}")

if __name__ == "__main__":
    folder = r"C:\Users\Admin\Downloads"
    extract_pdf_text(os.path.join(folder, "DOC090226-09022026121049.pdf"))
