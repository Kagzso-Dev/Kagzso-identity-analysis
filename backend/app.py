import os
import base64
import json
import logging
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from groq import Groq

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR.parent / ".env")

app = FastAPI(title="Kagzso Identity API")

session_history = []

origins = [
    "https://kagzso-identity-analysis.vercel.app",
    "https://kagzso-identity.netlify.app",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

_groq_api_key = os.environ.get("GROQ_API_KEY", "")
if not _groq_api_key:
    logger.error("GROQ_API_KEY is not set. All AI extraction will fail.")

try:
    client = Groq(api_key=_groq_api_key or "MISSING_KEY")
    logger.info(f"Groq client initialized. Key present: {bool(_groq_api_key)}")
except Exception as e:
    logger.error(f"Failed to initialize Groq client: {e}")
    client = None

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

VISION_PROMPT = """You are an expert at reading Indian identity documents.

Look at this document image and extract the following fields into a JSON object:
- type: one of "AADHAAR", "PAN CARD", "VOTER ID", "DRIVING LICENSE", "PASSPORT", "UNKNOWN"
- name: full name of the cardholder (not father's name)
- father_name: father or spouse name (look for S/O, D/O, C/O, W/O prefixes)
- id_number: the primary ID number (Aadhaar: 12 digits like "1234 5678 9012", PAN: "ABCDE1234F", etc.)
- dob: date of birth as DD/MM/YYYY or DD-MM-YYYY
- location: full address, city, or state on the document

Rules:
- Be lenient with low quality or partially visible text
- Set any field you cannot read to "-"
- Return ONLY a valid JSON object — no markdown, no explanation

Example: {"type":"AADHAAR","name":"Rahul Sharma","father_name":"Suresh Sharma","id_number":"1234 5678 9012","dob":"15/08/1990","location":"Mumbai, Maharashtra"}"""

OCR_LLM_PROMPT = """You are an expert Indian KYC document extractor. OCR text is often noisy with garbled characters or mixed Hindi/English.

Analyze the OCR text and extract fields into a JSON object.

Type detection:
- AADHAAR: "Aadhaar", "UIDAI", "Unique Identification", "आधार", or 12-digit groups (xxxx xxxx xxxx)
- PAN CARD: "Income Tax", "Permanent Account Number", or 10-char ABCDE1234F pattern
- VOTER ID: "Election Commission", "EPIC", "Voter"
- DRIVING LICENSE: "Driving Licence", "Transport", "DL No"
- PASSPORT: "Republic of India", "Passport No", "Nationality"

Fields:
- name: cardholder full name
- father_name: father/spouse name (S/O, D/O, C/O, W/O prefix)
- id_number: primary ID number
- dob: DD-MM-YYYY or DD/MM/YYYY
- location: address, city, or state

Return ONLY valid JSON. Unknown fields set to "-".

{{"type":"AADHAAR","name":"-","father_name":"-","id_number":"-","dob":"-","location":"-"}}

OCR TEXT:
{raw_text}"""

# ---------------------------------------------------------------------------
# Groq Vision extraction — PRIMARY method (no Tesseract required)
# ---------------------------------------------------------------------------

VISION_MODELS = [
    "llama-3.2-11b-vision-preview",
    "llama-3.2-90b-vision-preview",
]

def extract_with_vision(contents: bytes, content_type: str) -> dict | None:
    """Try each Groq Vision model in sequence; return first successful result."""
    if client is None or not _groq_api_key:
        logger.warning("Vision extraction skipped: Groq client not ready or API key missing.")
        return None

    mime = content_type if content_type in ("image/jpeg", "image/png", "image/webp", "image/gif") else "image/jpeg"
    b64 = base64.b64encode(contents).decode("utf-8")

    for model in VISION_MODELS:
        try:
            logger.info(f"Trying Groq Vision model: {model}")
            completion = client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                        {"type": "text", "text": VISION_PROMPT},
                    ],
                }],
                temperature=0,
                max_tokens=512,
            )

            raw = completion.choices[0].message.content.strip()
            logger.info(f"Vision ({model}) raw response: {raw[:400]}")

            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                logger.info(f"Vision extraction result ({model}): {data}")
                return data

            logger.warning(f"Vision model {model} returned no JSON object.")

        except Exception as e:
            logger.error(f"Vision model {model} failed: {e}")
            # Try next model

    logger.error("All vision models failed.")
    return None

# ---------------------------------------------------------------------------
# Tesseract OCR — FALLBACK (local dev only; not installed on Render Python runtime)
# ---------------------------------------------------------------------------

def tesseract_available() -> bool:
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False

def preprocess_image_variants(contents: bytes) -> list:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return []

    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return []

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    upscaled = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    variants = []

    # block=11 is correct for fine ID-card text (31 is too coarse)
    thresh_adapt = cv2.adaptiveThreshold(
        upscaled, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    variants.append(thresh_adapt)

    _, thresh_otsu = cv2.threshold(upscaled, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    variants.append(thresh_otsu)

    denoised = cv2.fastNlMeansDenoising(upscaled, h=10)
    thresh_denoised = cv2.adaptiveThreshold(
        denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    variants.append(thresh_denoised)

    variants.append(upscaled)
    variants.append(gray)

    return variants

def run_tesseract_ocr(contents: bytes) -> str:
    import pytesseract

    if os.name == "nt":
        pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    else:
        pytesseract.pytesseract.tesseract_cmd = "/usr/bin/tesseract"

    variants = preprocess_image_variants(contents)
    if not variants:
        logger.error("Could not generate image variants for Tesseract.")
        return ""

    psm_modes = ["--oem 3 --psm 4", "--oem 3 --psm 6", "--oem 3 --psm 3", "--oem 3 --psm 11"]
    best = ""

    for i, img in enumerate(variants):
        for psm in psm_modes:
            try:
                candidate = pytesseract.image_to_string(img, config=psm)
                if len(candidate.strip()) > len(best.strip()):
                    best = candidate
                    logger.info(f"Tesseract update: variant={i} psm={psm} chars={len(best.strip())}")
            except Exception as e:
                logger.warning(f"Tesseract attempt failed (variant={i}, {psm}): {e}")
        if len(best.strip()) >= 60:
            break

    return best

def llm_from_ocr_text(raw_text: str) -> dict | None:
    """Send raw OCR text to Groq LLM for structured extraction."""
    if client is None or not raw_text.strip():
        return None
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": OCR_LLM_PROMPT.format(raw_text=raw_text)}],
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(completion.choices[0].message.content)
        logger.info(f"LLM-from-OCR result: {data}")
        return data
    except Exception as e:
        logger.error(f"LLM OCR extraction failed: {e}", exc_info=True)
        return None

# ---------------------------------------------------------------------------
# PDF extraction — uses PyMuPDF native text layer (no Tesseract needed for digital PDFs)
# ---------------------------------------------------------------------------

def extract_pdf_text(contents: bytes) -> str:
    import fitz

    doc = fitz.open(stream=contents, filetype="pdf")
    full_text = ""

    for page_num, page in enumerate(doc):
        # Native text layer (works for digital/selectable PDFs — no Tesseract)
        text = page.get_text("text").strip()
        if text:
            logger.info(f"PDF page {page_num}: extracted {len(text)} chars via native text layer.")
            full_text += text + "\n"
        else:
            # Scanned page — try Tesseract if available
            logger.warning(f"PDF page {page_num}: no native text. Checking Tesseract availability.")
            if tesseract_available():
                try:
                    import pytesseract
                    pytesseract.pytesseract.tesseract_cmd = (
                        r"C:\Program Files\Tesseract-OCR\tesseract.exe" if os.name == "nt" else "/usr/bin/tesseract"
                    )
                    mat = fitz.Matrix(2.0, 2.0)
                    pix = page.get_pixmap(matrix=mat)
                    img_bytes = pix.tobytes("png")
                    variants = preprocess_image_variants(img_bytes)
                    if variants:
                        ocr_text = pytesseract.image_to_string(variants[0], config="--oem 3 --psm 6")
                        full_text += ocr_text + "\n"
                        logger.info(f"PDF page {page_num}: Tesseract extracted {len(ocr_text)} chars.")
                except Exception as e:
                    logger.warning(f"PDF Tesseract fallback failed on page {page_num}: {e}")
            else:
                logger.warning(f"PDF page {page_num} is scanned but Tesseract is not available on this host.")

    return full_text.strip()

# ---------------------------------------------------------------------------
# Regex boost for Aadhaar
# ---------------------------------------------------------------------------

def clean_ocr_text(text: str) -> str:
    text = text.replace("|", "I").replace("(", "").replace(")", "")
    text = re.sub(r"\n+", "\n", text)
    text = re.sub(r" +", " ", text)
    return text.strip()

def regex_boost(data: dict, raw_text: str) -> dict:
    aadhaar_re = r'\d{4}[\s\-]\d{4}[\s\-]\d{4}'
    dob_re = r'\d{2}[\/\-]\d{2}[\/\-]\d{4}'

    if data.get("id_number", "-") == "-":
        m = re.search(aadhaar_re, raw_text)
        if m:
            data["id_number"] = m.group(0)
            logger.info(f"Regex boosted id_number: {data['id_number']}")

    if data.get("dob", "-") == "-":
        m = re.search(dob_re, raw_text)
        if m:
            data["dob"] = m.group(0)
            logger.info(f"Regex boosted dob: {data['dob']}")

    return data

def empty_response(filename: str, reason: str) -> dict:
    logger.error(f"Returning UNKNOWN for '{filename}'. Reason: {reason}")
    return {
        "type": "UNKNOWN", "document_type": "UNKNOWN",
        "name": "-", "father_name": "-", "id_number": "-",
        "dob": "-", "location": "-", "address": "-",
        "filename": filename, "error": reason,
    }

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/")
async def root():
    return {"status": "ok", "message": "Kagzso Identity API is online"}

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "message": "healthy",
        "tesseract_available": tesseract_available(),
        "groq_client_initialized": client is not None,
        "groq_api_key_set": bool(_groq_api_key),
        "vision_models": VISION_MODELS,
    }

@app.post("/scan")
@app.post("/upload")
@app.post("/api/scan")
async def upload_file(file: UploadFile = File(...)):
    contents = await file.read()
    logger.info(f"--- Upload --- file={file.filename!r} type={file.content_type} size={len(contents)} bytes")

    if not file.content_type.startswith(("image/", "application/pdf")):
        raise HTTPException(status_code=400, detail="Unsupported file type. Send an image or PDF.")

    if client is None or not _groq_api_key:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY is not set. Set it in Render → Environment Variables.")

    try:
        data = None

        # ── PDF ──────────────────────────────────────────────────────────────
        if file.content_type == "application/pdf":
            raw_text = clean_ocr_text(extract_pdf_text(contents))
            logger.info(f"PDF text ({len(raw_text)} chars):\n{raw_text[:500]}")

            if not raw_text.strip():
                return empty_response(file.filename, "Could not extract text from PDF. It may be a fully scanned PDF without a text layer and Tesseract is unavailable on this host.")

            data = llm_from_ocr_text(raw_text)

        # ── IMAGE ─────────────────────────────────────────────────────────────
        else:
            # Step 1: Groq Vision (primary — works everywhere, no Tesseract needed)
            data = extract_with_vision(contents, file.content_type)

            # Step 2: Tesseract + LLM fallback (works locally; also on Render after buildCommand fix)
            if data is None or data.get("type") == "UNKNOWN":
                logger.info("Vision returned UNKNOWN/None — trying Tesseract fallback.")
                if tesseract_available():
                    raw_text = clean_ocr_text(run_tesseract_ocr(contents))
                    logger.info(f"Tesseract OCR ({len(raw_text)} chars):\n{raw_text[:500]}")
                    if raw_text.strip():
                        fallback = llm_from_ocr_text(raw_text)
                        # Accept Tesseract result if it extracted ANY real field, even if type=UNKNOWN
                        if fallback:
                            has_data = any(
                                fallback.get(f, "-") not in ("-", "", None)
                                for f in ("name", "id_number", "dob", "location")
                            )
                            if has_data or data is None:
                                data = fallback
                                logger.info("Using Tesseract+LLM result.")
                else:
                    logger.warning("Tesseract not available on this host — Vision API is the only extraction path.")

        if not data:
            tess = tesseract_available()
            key_ok = bool(_groq_api_key)
            return empty_response(
                file.filename,
                f"All extraction methods failed. "
                f"[groq_key={'SET' if key_ok else 'MISSING'}, tesseract={'available' if tess else 'not installed'}] "
                f"Try a clearer image or check server logs."
            )

        # Normalise keys for frontend
        data["document_type"] = data.get("type", "UNKNOWN")
        data["address"] = data.get("location", "-")
        data["filename"] = file.filename

        # Regex boost: recover Aadhaar number/DOB if model missed them
        if data.get("type") in ("AADHAAR", "UNKNOWN"):
            combined = " ".join(str(v) for v in data.values())
            data = regex_boost(data, combined)

        logger.info(f"Final response: {data}")
        session_history.append(data)
        return data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unhandled error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")

@app.get("/export")
@app.get("/api/export")
async def export_excel():
    import pandas as pd
    if not session_history:
        return {"error": "No data to export."}
    df = pd.DataFrame(session_history)
    file_path = str(BASE_DIR / "session_data.xlsx")
    df.to_excel(file_path, index=False)
    return FileResponse(file_path, filename="Kagzso_Extraction.xlsx")

@app.delete("/clear")
@app.delete("/api/clear")
async def clear():
    session_history.clear()
    return {"status": "cleared"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
