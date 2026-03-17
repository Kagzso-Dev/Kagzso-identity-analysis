import os
import io
import json
import logging
import re
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np
import pandas as pd
import pytesseract
from PIL import Image
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from groq import Groq

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
load_dotenv()

app = FastAPI(title="Kagzso Identity API")

# Store session history in memory
session_history = []

# CORS Configuration
origins = [
    "https://kagzso-identity.netlify.app",
    "http://localhost:5173",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tesseract Configuration for Linux (Render) and Windows
if os.name == 'nt':  # Windows
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
else:  # Linux (Render)
    pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

# Initialize Groq client
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

ID_PROMPT = """
You are an intelligent Indian document data extractor specialized in KYC documents (Aadhaar, PAN, Voter ID, Passport, DL).

Task:
Analyze the OCR text provided and extract information into a structured JSON format.

Detection Rules:
- Identify "document_type" as: "AADHAAR", "PAN CARD", "VOTER ID", "DRIVING LICENSE", "PASSPORT", or "UNKNOWN".
- Aadhaar: 12-digit number (xxxx xxxx xxxx).
- PAN: 10-char alphanumeric (e.g., ABCDE1234F).
- Voter ID: EPIC number.
- DL: License number.

Field Mapping:
- name: Full name.
- father_name: Father's or Spouse's name.
- id_number: Primary ID number.
- dob: Date of birth (DD-MM-YYYY).
- location: Full address or state.

Return ONLY a JSON object. No markdown, no intro.
If a field is missing, set it to "-".

JSON Structure:
{{
  "document_type": "-",
  "name": "-",
  "father_name": "-",
  "id_number": "-",
  "dob": "-",
  "location": "-"
}}

OCR TEXT:
{raw_text}
"""

def preprocess_image(contents: bytes) -> np.ndarray:
    """Apply grayscale and thresholding for better OCR results."""
    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Binary thresholding + Otsu's thresholding
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return thresh

def clean_ocr_text(text: str) -> str:
    """Pre-parse cleaning for common OCR errors."""
    # Remove excessive newlines and weird symbols
    text = re.sub(r'[^\w\s\-\/\:\.\,]', '', text)
    text = re.sub(r'\n+', '\n', text)
    return text.strip()

def extract_text_from_pdf(contents: bytes) -> str:
    import fitz  # PyMuPDF
    doc = fitz.open(stream=contents, filetype="pdf")
    full_text = ""
    for page in doc:
        # Increase resolution for better OCR
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        
        processed_img = preprocess_image(img_bytes)
        full_text += pytesseract.image_to_string(processed_img, config='--psm 3') + "\n"
    return full_text

@app.get("/health")
@app.get("/api/health")
async def health():
    return {"status": "ok", "tesseract_path": pytesseract.pytesseract.tesseract_cmd}

@app.post("/scan")
@app.post("/upload")
@app.post("/api/scan")
async def scan_document(file: UploadFile = File(...)):
    logger.info(f"Received file: {file.filename}, Content-Type: {file.content_type}")
    
    if not file.content_type.startswith(('image/', 'application/pdf')):
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload an image or PDF.")

    try:
        contents = await file.read()
        
        if file.content_type == "application/pdf" or file.filename.lower().endswith('.pdf'):
            raw_text = extract_text_from_pdf(contents)
        else:
            processed_img = preprocess_image(contents)
            if processed_img is None:
                raise ValueError("Failed to process image")
            raw_text = pytesseract.image_to_string(processed_img, config='--psm 3')

        raw_text = clean_ocr_text(raw_text)
        logger.info(f"Extracted Raw Text Snippet: {raw_text[:200]}...")

        if not raw_text.strip():
            logger.warning("No text detected in OCR process.")
            return {
                "name": "-", "father_name": "-", "id_number": "-", 
                "dob": "-", "location": "-", "document_type": "UNKNOWN",
                "error": "No text detected"
            }

        # Call Groq for intelligent parsing
        prompt = ID_PROMPT.format(raw_text=raw_text)
        
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"}
        )
        
        result_json = completion.choices[0].message.content
        data = json.loads(result_json)
        data["filename"] = file.filename
        
        logger.info(f"Parsed Result: {data}")
        session_history.append(data)
        
        return data

    except Exception as e:
        logger.error(f"Processing Error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/export")
@app.get("/api/export")
async def export_excel():
    if not session_history:
        raise HTTPException(status_code=400, detail="No scan data available.")

    try:
        df = pd.DataFrame(session_history)
        file_path = BASE_DIR / "scan_results.xlsx"
        df.to_excel(file_path, index=False)
        return FileResponse(path=file_path, filename="extracted_data.xlsx")
    except Exception as e:
        logger.error(f"Export Error: {e}")
        raise HTTPException(status_code=500, detail="Export failed")

@app.delete("/clear")
@app.delete("/api/clear")
async def clear_history():
    global session_history
    session_history = []
    return {"message": "History cleared"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
