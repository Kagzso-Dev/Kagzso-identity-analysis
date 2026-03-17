import fitz
import os

def extract_pdf_fitz(path):
    print(f"\n--- EXTRACTING PDF (FITZ): {path} ---")
    try:
        doc = fitz.open(path)
        for i in range(len(doc)):
            page = doc[i]
            print(f"--- PAGE {i+1} ---")
            print(page.get_text())
    except Exception as e:
        print(f"[ERROR]: {e}")

if __name__ == "__main__":
    folder = r"C:\Users\Admin\Downloads"
    extract_pdf_fitz(os.path.join(folder, "sample_document.pdf"))
