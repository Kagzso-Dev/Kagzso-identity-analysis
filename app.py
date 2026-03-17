import os
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import pytesseract
from PIL import Image
import io
from groq import Groq
import json
import pandas as pd
from dotenv import load_dotenv
from typing import List

BASE_DIR = Path(__file__).parent

load_dotenv()

app = FastAPI()

# Store session history in memory (could be a DB in prod)
session_history = []

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tesseract path
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

# Initialize Groq client
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

ID_PROMPT = """
You are an intelligent Indian document data extractor specialized in KYC documents.

Task:
Analyze the OCR text provided and extract information into a structured JSON format.

Detection Rules:
- Identify the "document_type" as one of: "AADHAAR", "PAN CARD", "VOTER ID", "DRIVING LICENSE", "PASSPORT", "RATION CARD", or "UNKNOWN".
- For Aadhaar: "id_number" is a 12-digit number (e.g., 0000 1111 2222).
- For PAN Cards: "id_number" is the Permanent Account Number (10 alphanumeric characters).
- For Voter IDs: "id_number" is the EPIC number (e.g., KKD1933993).
- For Driving License: "id_number" is the DL number (e.g., DL-11 2024000123).
- For Passport: "id_number" is the Passport number (e.g., N1234567).

Field Mapping:
- "name": Full name of the individual.
- "dob": Date of birth in DD-MM-YYYY format if possible.
- "gender": Male, Female, or Third Gender.
- "id_number": The primary identifier number on the document.
- "father_name": Father's or Spouse's name.
- "address": Full residential address.
- "issue_date": Date of issue.
- "expiry_date": Date of expiry (especially for DL and Passport).

Return ONLY the JSON object. No explanations.
If a field is not found, set it to null.

JSON Structure:
{{
  "document_type": "",
  "name": "",
  "dob": "",
  "gender": "",
  "id_number": "",
  "father_name": "",
  "address": "",
  "issue_date": "",
  "expiry_date": ""
}}

OCR TEXT FROM IMAGE:
{raw_text}
"""

@app.get("/health")
async def health():
    return {"status": "ok"}

def extract_text_from_pdf(contents: bytes) -> str:
    import fitz  # PyMuPDF
    doc = fitz.open(stream=contents, filetype="pdf")
    full_text = ""
    for page in doc:
        mat = fitz.Matrix(2.0, 2.0)
        pix = page.get_pixmap(matrix=mat)
        image = Image.open(io.BytesIO(pix.tobytes("png")))
        full_text += pytesseract.image_to_string(image) + "\n"
    return full_text


@app.post("/scan")
async def scan_document(file: UploadFile = File(...)):
    try:
        contents = await file.read()

        # Handle PDF vs image
        if file.content_type == "application/pdf" or (file.filename or "").lower().endswith(".pdf"):
            raw_text = extract_text_from_pdf(contents)
        else:
            image = Image.open(io.BytesIO(contents))
            raw_text = pytesseract.image_to_string(image)

        if not raw_text.strip():
            return {"error": "No text detected in image"}

        # Call Groq
        prompt = ID_PROMPT.format(raw_text=raw_text)
        
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            response_format={"type": "json_object"}
        )
        
        result_json = completion.choices[0].message.content
        data = json.loads(result_json)
        data["filename"] = file.filename # Add filename for history tracking
        
        # Add to session history
        session_history.append(data)
        
        return data

    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/export")
async def export_excel():
    if not session_history:
        raise HTTPException(status_code=400, detail="No scan data available to export.")

    try:
        # Create DataFrame (exclude raw_text from Excel if desired)
        df = pd.DataFrame(session_history)
        
        # Remove raw_text for a clean excel sheet
        if 'raw_text' in df.columns:
            df = df.drop(columns=['raw_text'])

        file_path = str(BASE_DIR / "scan_results.xlsx")
        df.to_excel(file_path, index=False)
        
        return FileResponse(path=file_path, filename="extracted_documents.xlsx", media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    except Exception as e:
        print(f"Export Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate Excel file.")

@app.delete("/clear")
async def clear_history():
    global session_history
    session_history = []
    return {"message": "History cleared"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
