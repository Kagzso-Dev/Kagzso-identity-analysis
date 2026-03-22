# Standard library imports only at top level for resilience
import os
import io
import json
import logging
import re
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from groq import Groq

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR.parent / ".env")

app = FastAPI(title="Kagzso Identity API")

# Store session history in memory
session_history = []

# CORS Configuration
origins = [
    "https://kagzso-identity-analysis.vercel.app",
    "https://kagzso-identity.netlify.app",
    "http://localhost:5173",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tesseract Configuration will happen inside functions as needed

# Initialize Groq client
try:
    client = Groq(api_key=os.environ.get("GROQ_API_KEY") or "MISSING_KEY")
except Exception as e:
    logger.error(f"Failed to initialize Groq client: {e}")
    client = None

ID_PROMPT = """
You are an expert Indian KYC document extractor. OCR text from scanned identity cards is often noisy with missing spaces, garbled characters, or mixed Hindi/English words.

Task: Analyze the OCR text and extract fields into a structured JSON object.

Detection Rules:
- Set "type" to one of: "AADHAAR", "PAN CARD", "VOTER ID", "DRIVING LICENSE", "PASSPORT", or "UNKNOWN".
- AADHAAR: look for keywords like "Aadhaar", "UIDAI", "Unique Identification", "आधार", or a 12-digit number in groups (xxxx xxxx xxxx). Even partial matches or noisy OCR variants count.
- PAN CARD: look for "Income Tax", "Permanent Account Number", or a 10-char pattern like ABCDE1234F.
- VOTER ID: look for "Election Commission", "EPIC", "Voter".
- DRIVING LICENSE: look for "Driving Licence", "Transport", "DL No".
- PASSPORT: look for "Republic of India", "Passport No", "Nationality".
- Be lenient — OCR text may be garbled. Infer type from any recognizable keywords or number patterns.

Field Mapping:
- name: Full name of the cardholder (not father's name).
- father_name: Father's name (prefixed by "S/O", "D/O", "C/O", "Father") or spouse name.
- id_number: The primary ID number (12-digit Aadhaar, 10-char PAN, etc.).
- dob: Date of birth in DD-MM-YYYY or DD/MM/YYYY format.
- location: Full address, state, or city found in the document.

Return ONLY a valid JSON object. No markdown, no explanation.
If a field cannot be determined, set it to "-".

JSON Structure:
{{
  "type": "AADHAAR",
  "name": "-",
  "father_name": "-",
  "id_number": "-",
  "dob": "-",
  "location": "-"
}}

OCR TEXT:
{raw_text}
"""

def preprocess_image(contents: bytes):
    """Apply grayscale, upscaling, and adaptive thresholding for better OCR results."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        logger.error("OpenCV or NumPy not found.")
        return None

    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return None

    # 1. Grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 2. Upscale 2x
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    # 3. Adaptive thresholding
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 2
    )

    return thresh

def clean_ocr_text(text: str) -> str:
    """Pre-parse cleaning for common OCR errors."""
    # Basic cleaning
    text = text.replace('|', 'I').replace('(', '').replace(')', '')
    # Remove multiple spaces/newlines
    text = re.sub(r'\n+', '\n', text)
    text = re.sub(r' +', ' ', text)
    return text.strip()

def regex_extract_aadhaar(text: str):
    """Fallback/Booster regex for Aadhaar documents."""
    # Allow any whitespace or dash between groups (OCR often misreads spacing)
    aadhaar_pattern = r'\d{4}[\s\-]\d{4}[\s\-]\d{4}'
    dob_pattern = r'\d{2}[\/\-]\d{2}[\/\-]\d{4}'

    number = re.search(aadhaar_pattern, text)
    dob = re.search(dob_pattern, text)

    return {
        "id_number": number.group(0) if number else None,
        "dob": dob.group(0) if dob else None
    }

def extract_text_from_pdf(contents: bytes) -> str:
    import fitz  # PyMuPDF
    doc = fitz.open(stream=contents, filetype="pdf")
    full_text = ""
    for page in doc:
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)
        img_bytes = pix.tobytes("png")
        processed_img = preprocess_image(img_bytes)
        full_text += pytesseract.image_to_string(processed_img, config='--oem 3 --psm 6') + "\n"
    return full_text

@app.get("/")
async def root():
    return {"status": "ok", "message": "Kagzso Identity API is online"}

@app.get("/api/health")
async def health():
    return {"status": "ok", "message": "healthy"}

@app.post("/scan")
@app.post("/upload")
@app.post("/api/scan")
async def upload_file(file: UploadFile = File(...)):
    import pytesseract
    import numpy as np
    import cv2
    if os.name == 'nt':
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    else:
        pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

    # Log file details
    contents = await file.read()
    file_size = len(contents)
    logger.info(f"Incoming Request: File={file.filename}, Type={file.content_type}, Size={file_size} bytes")
    
    if not file.content_type.startswith(('image/', 'application/pdf')):
        raise HTTPException(status_code=400, detail="Unsupported file format.")

    try:
        # OCR Processing
        if file.content_type == "application/pdf":
            raw_text = extract_text_from_pdf(contents)
        else:
            processed_img = preprocess_image(contents)
            if processed_img is None:
                raise ValueError("Could not decode image.")
            # Try PSM 6 (uniform block) first, fall back to PSM 11 (sparse text)
            raw_text = pytesseract.image_to_string(processed_img, config='--oem 3 --psm 6')
            if len(raw_text.strip()) < 40:
                raw_text = pytesseract.image_to_string(processed_img, config='--oem 3 --psm 11')
            # Last resort: try on the original (non-preprocessed) image
            if len(raw_text.strip()) < 40:
                nparr = np.frombuffer(contents, np.uint8)
                orig_img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
                if orig_img is not None:
                    raw_text = pytesseract.image_to_string(orig_img, config='--oem 3 --psm 6')

        raw_text = clean_ocr_text(raw_text)
        logger.info(f"Extracted OCR Text snippet:\n{raw_text[:500]}")

        if not raw_text.strip():
            logger.error("OCR extraction resulted in empty text.")
            return {
                "type": "UNKNOWN",
                "document_type": "UNKNOWN",
                "name": "-",
                "father_name": "-",
                "id_number": "-",
                "dob": "-",
                "location": "-",
                "address": "-",
                "error": "Failed to extract text from document. Please ensure the image is clear."
            }

        # Intelligent Extraction with LLM (Groq)
        prompt = ID_PROMPT.format(raw_text=raw_text)
        
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"}
        )
        
        result_json = completion.choices[0].message.content
        data = json.loads(result_json)
        
        # Add compatibility keys for frontend
        data["document_type"] = data.get("type", "-")
        data["address"] = data.get("location", "-")
        data["filename"] = file.filename
        
        # Verify Aadhaar with regex if type is Aadhaar
        if data.get("type") == "AADHAAR" or "Aadhaar" in raw_text:
            reg_data = regex_extract_aadhaar(raw_text)
            if reg_data["id_number"] and data["id_number"] == "-":
                data["id_number"] = reg_data["id_number"]
            if reg_data["dob"] and data["dob"] == "-":
                data["dob"] = reg_data["dob"]

        logger.info(f"Final Data: {data}")
        session_history.append(data)
        
        return data

    except Exception as e:
        logger.error(f"Error processing document: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error during OCR processing.")

@app.get("/export")
@app.get("/api/export")
async def export_excel():
    import pandas as pd
    if not session_history:
        return {"error": "No data available."}
    df = pd.DataFrame(session_history)
    file_path = "session_data.xlsx"
    df.to_excel(file_path, index=False)
    return FileResponse(file_path, filename="Kagzso_Extraction.xlsx")

@app.delete("/clear")
@app.delete("/api/clear")
async def clear():
    global session_history
    session_history = []
    return {"status": "cleared"}

if __name__ == "__main__":
    import uvicorn
    # Render uses the PORT environment variable, defaults to 10000 for Render
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)
