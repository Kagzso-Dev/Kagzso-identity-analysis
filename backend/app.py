import io
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
from PIL import Image

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
    # Vercel preview deployments get a unique hash in the subdomain, e.g.
    # kagzso-identity-analysis-abc123-user.vercel.app — cover them all with regex
    allow_origin_regex=r"https://kagzso-identity-analysis[a-zA-Z0-9\-]*\.vercel\.app",
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
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
# Image normalisation — handles any size / format before processing
# ---------------------------------------------------------------------------

# Target longest side for Vision API (keeps payload fast and under limits)
VISION_MAX_DIM = 1600
# Target shortest side for OCR (300 DPI equivalent for a credit-card doc)
OCR_MIN_SHORT = 900
# Hard cap on upscale factor to avoid OOM on huge originals
OCR_MAX_SCALE = 4.0


def normalise_for_vision(contents: bytes) -> tuple[bytes, str]:
    """
    Convert any image format → JPEG, resize so longest side ≤ VISION_MAX_DIM.
    Returns (jpeg_bytes, 'image/jpeg').
    Falls back to the original bytes on any error.
    """
    try:
        img = Image.open(io.BytesIO(contents))
        # Flatten transparency / palette modes
        if img.mode in ("RGBA", "P", "LA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
            img = bg
        elif img.mode != "RGB":
            img = img.convert("RGB")

        w, h = img.size
        longest = max(w, h)
        if longest > VISION_MAX_DIM:
            scale = VISION_MAX_DIM / longest
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            logger.info(f"Vision resize: {w}x{h} → {img.width}x{img.height}")

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88, optimize=True)
        result = buf.getvalue()
        logger.info(f"Vision image prepared: {len(contents)//1024}KB → {len(result)//1024}KB")
        return result, "image/jpeg"

    except Exception as e:
        logger.warning(f"normalise_for_vision failed ({e}); using original bytes.")
        return contents, "image/jpeg"


def normalise_for_ocr(contents: bytes) -> bytes:
    """
    Upscale small images so the shortest side reaches OCR_MIN_SHORT pixels.
    Large images are left unchanged (OCR handles them fine natively).
    Returns PNG bytes for lossless OCR input.
    """
    try:
        img = Image.open(io.BytesIO(contents))
        if img.mode != "RGB":
            img = img.convert("RGB")

        w, h = img.size
        shortest = min(w, h)
        if shortest < OCR_MIN_SHORT:
            scale = min(OCR_MIN_SHORT / shortest, OCR_MAX_SCALE)
            new_w, new_h = int(w * scale), int(h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            logger.info(f"OCR upscale: {w}x{h} → {new_w}x{new_h} (×{scale:.2f})")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    except Exception as e:
        logger.warning(f"normalise_for_tesseract failed ({e}); using original bytes.")
        return contents

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

VISION_PROMPT = """You are an expert OCR system specialised in Indian government identity documents.

Carefully examine every part of the image — including small print, watermarks, and partially visible text.

Identify the document type:
- AADHAAR: has "Aadhaar", "UIDAI", "Unique Identification Authority", "आधार", or a 12-digit number split as XXXX XXXX XXXX
- PAN CARD: has "Income Tax Department", "Permanent Account Number", or a 10-char code like ABCDE1234F
- VOTER ID: has "Election Commission of India", "EPIC No", or "Voter"
- DRIVING LICENSE: has "Driving Licence", "Transport Authority", or "DL No"
- PASSPORT: has "Republic of India", "Passport No", or travel document layout

Extract these fields into a single JSON object:
- type: document type from the list above, or "UNKNOWN"
- name: full name of the primary cardholder (NOT the father/spouse)
- father_name: name after S/O, D/O, C/O, or W/O prefix; "-" if not present
- id_number: the main identification number exactly as printed
- dob: date of birth in DD/MM/YYYY or DD-MM-YYYY format
- location: full address, district, state, or pincode visible on the document

Important rules:
- Read ALL text visible in the image, even if blurry or at an angle
- Aadhaar numbers: look for any 12-digit sequence, possibly split across lines
- For PAN: the 10-char alphanumeric code (e.g. ABCDE1234F)
- Set fields you genuinely cannot read to "-" — never guess
- Output ONLY the raw JSON object. No markdown, no code block, no explanation.

Example output:
{"type":"AADHAAR","name":"Priya Mehta","father_name":"Ramesh Mehta","id_number":"2345 6789 0123","dob":"04/03/1995","location":"12 MG Road, Pune, Maharashtra 411001"}"""

VISION_RETRY_PROMPT = """This is an Indian government identity document. I need you to read every number and word visible.

Focus on:
1. Any 12-digit number (could be Aadhaar): look for groups like XXXX XXXX XXXX
2. Any 10-character alphanumeric code (could be PAN): like ABCDE1234F
3. A person's name (usually the largest text after any heading)
4. A date in DD/MM/YYYY format (date of birth)
5. Any address text

Return ONLY this JSON (fill in what you can see, use "-" for anything not visible):
{"type":"AADHAAR","name":"-","father_name":"-","id_number":"-","dob":"-","location":"-"}"""

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
# Groq Vision extraction — PRIMARY (no Tesseract required)
# ---------------------------------------------------------------------------

VISION_MODELS = [
    "llama-3.2-11b-vision-preview",
    "llama-3.2-90b-vision-preview",
]


def _call_vision_model(model: str, b64: str, mime: str, prompt: str) -> dict | None:
    """Call one Vision model with the given prompt. Returns parsed dict or None."""
    completion = client.chat.completions.create(
        model=model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                {"type": "text", "text": prompt},
            ],
        }],
        temperature=0,
        max_tokens=600,
    )
    raw = completion.choices[0].message.content.strip()
    logger.info(f"Vision ({model}) raw: {raw[:500]}")
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    return None


def _has_useful_fields(data: dict) -> bool:
    """Return True if at least one real field was extracted (not just type)."""
    return any(
        data.get(f, "-") not in ("-", "", None, "UNKNOWN")
        for f in ("name", "id_number", "dob", "location", "father_name")
    )


def extract_with_vision(contents: bytes) -> dict | None:
    """
    Normalise image → try each Vision model with the full prompt.
    If result is UNKNOWN or has no useful fields, retry with the focused retry prompt.
    """
    if client is None or not _groq_api_key:
        logger.warning("Vision skipped: Groq client not ready or API key missing.")
        return None

    vision_bytes, mime = normalise_for_vision(contents)
    b64 = base64.b64encode(vision_bytes).decode("utf-8")

    best: dict | None = None

    for model in VISION_MODELS:
        # Pass 1 — full detailed prompt
        try:
            logger.info(f"Vision pass 1 — model: {model}")
            data = _call_vision_model(model, b64, mime, VISION_PROMPT)
            if data:
                logger.info(f"Vision pass 1 result ({model}): {data}")
                if data.get("type") != "UNKNOWN" or _has_useful_fields(data):
                    return data          # good result — stop here
                best = data             # keep as candidate, try retry pass
        except Exception as e:
            logger.error(f"Vision pass 1 ({model}) failed: {e}")

        # Pass 2 — focused retry prompt when pass 1 returned UNKNOWN
        try:
            logger.info(f"Vision pass 2 (retry) — model: {model}")
            data2 = _call_vision_model(model, b64, mime, VISION_RETRY_PROMPT)
            if data2 and _has_useful_fields(data2):
                logger.info(f"Vision pass 2 result ({model}): {data2}")
                return data2
        except Exception as e:
            logger.error(f"Vision pass 2 ({model}) failed: {e}")

    logger.error("All vision model passes failed or returned no useful data.")
    return best  # return best attempt (even if UNKNOWN) so regex_boost can try

# ----------------------------------------------------------
# EasyOCR — Portability fallback (replaces Tesseract)
# ----------------------------------------------------------

_reader = None

def get_easyocr_reader():
    """Lazy initialization of EasyOCR reader to save RAM on startup."""
    global _reader
    if _reader is None:
        try:
            import easyocr
            # Load English and Hindi (best for Indian IDs)
            # Use gpu=False for standard Render CPU instances
            _reader = easyocr.Reader(['en', 'hi'], gpu=False)
            logger.info("EasyOCR Reader initialized (en/hi).")
        except Exception as e:
            logger.error(f"Failed to initialize EasyOCR: {e}")
    return _reader


def ocr_available() -> bool:
    """Check if EasyOCR is ready to use."""
    return get_easyocr_reader() is not None


def run_easy_ocr(contents: bytes) -> str:
    """
    1. Convert bytes → NumPy/OpenCV image
    2. Run EasyOCR on the image array
    3. Return joined string of all detected text
    """
    import numpy as np
    import cv2

    reader = get_easyocr_reader()
    if not reader:
        return ""

    try:
        # Convert bytes to cv2 image array
        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            logger.error("EasyOCR: Could not decode image bytes with OpenCV.")
            return ""

        # Pre-process for OCR (Grayscale)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Basic OCR
        results = reader.readtext(gray, detail=0)
        full_text = " ".join(results)

        logger.info(f"EasyOCR success: {len(full_text)} chars extracted.")
        logger.debug(f"FULL OCR TEXT: {full_text}")
        return full_text

    except Exception as e:
        logger.error(f"EasyOCR failed: {e}")
        return ""


# Preprocessing and running Tesseract is removed in favor of EasyOCR's native handling


def llm_from_ocr_text(raw_text: str) -> dict | None:
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
# PDF extraction — native text layer + Tesseract for scanned pages
# ---------------------------------------------------------------------------

def pdf_page_to_image(contents: bytes, page_num: int = 0, scale: float = 2.0) -> bytes:
    """Render a PDF page to PNG bytes using PyMuPDF."""
    import fitz
    doc = fitz.open(stream=contents, filetype="pdf")
    page = doc[page_num]
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
    return pix.tobytes("png")


def extract_pdf_text(contents: bytes) -> str:
    import fitz
    doc = fitz.open(stream=contents, filetype="pdf")
    full_text = ""

    for page_num, page in enumerate(doc):
        text = page.get_text("text").strip()
        if text:
            logger.info(f"PDF page {page_num}: {len(text)} chars (native text layer).")
            full_text += text + "\n"
        else:
            logger.warning(f"PDF page {page_num}: no native text — trying EasyOCR.")
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            img_bytes = pix.tobytes("png")
            page_text = run_easy_ocr(img_bytes)
            full_text += page_text + "\n"

    return full_text.strip()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def clean_ocr_text(text: str) -> str:
    text = text.replace("|", "I").replace("(", "").replace(")", "")
    text = re.sub(r"\n+", "\n", text)
    text = re.sub(r" +", " ", text)
    return text.strip()


def regex_boost(data: dict, raw_text: str) -> dict:
    # Basic normalization
    text_clean = re.sub(r'[^a-zA-Z0-9\s\-\/]', ' ', raw_text)
    doc_type = data.get("type", "UNKNOWN")

    # 1. Aadhaar Number (12 digits)
    aadhaar_pat = r'\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b'
    # 2. PAN (ABCDE1234F)
    pan_pat = r'\b[A-Z]{5}\d{4}[A-Z]\b'
    # 3. DOB (DD/MM/YYYY or DD-MM-YYYY)
    dob_pat = r'\b\d{2}[\s\/\-]\d{2}[\s\/\-]\d{4}\b'

    if data.get("id_number", "-") in ("-", "", None):
        m = re.search(aadhaar_pat, text_clean)
        if m:
            data["id_number"] = m.group(0)
            if doc_type == "UNKNOWN": data["type"] = "AADHAAR"
            logger.info(f"Regex Boost: Found Aadhaar ID: {data['id_number']}")
        else:
            m = re.search(pan_pat, text_clean)
            if m:
                data["id_number"] = m.group(0)
                if doc_type == "UNKNOWN": data["type"] = "PAN CARD"
                logger.info(f"Regex Boost: Found PAN ID: {data['id_number']}")

    if data.get("dob", "-") in ("-", "", None):
        m = re.search(dob_pat, text_clean)
        if m:
            data["dob"] = m.group(0).replace(" ", "/")
            logger.info(f"Regex Boost: Found DOB: {data['dob']}")

    if data.get("name", "-") in ("-", "", None):
        # Fallback Name Search: Capitalized blocks that aren't headers
        name_m = re.search(r'\b([A-Z]{3,}\s+[A-Z]{3,}(?:\s+[A-Z]{3,})?)\b', raw_text)
        if name_m:
            candidate = name_m.group(1).strip()
            # Simple header blacklist
            if not any(x in candidate for x in ["INDIA", "GOVERNMENT", "INCOME", "TAX", "CARD", "IDENTIFICATION"]):
                data["name"] = candidate
                logger.info(f"Regex Boost: Found Potential Name: {data['name']}")

    return data


def empty_response(filename: str, reason: str) -> dict:
    logger.error(f"UNKNOWN result for '{filename}': {reason}")
    return {
        "type": "UNKNOWN", "document_type": "UNKNOWN",
        "name": "-", "father_name": "-", "id_number": "-",
        "dob": "-", "location": "-", "address": "-",
        "filename": filename, "error": reason,
    }

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.options("/{rest:path}")
async def preflight_handler():
    """Explicit OPTIONS handler so CORS preflight always gets 200."""
    return {}

@app.get("/")
async def root():
    return {"status": "ok", "message": "Kagzso Identity API is online"}


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "message": "healthy",
        "ocr_available": ocr_available(),
        "groq_client_initialized": client is not None,
        "groq_api_key_set": bool(_groq_api_key),
        "vision_models": VISION_MODELS,
    }


@app.post("/scan")
@app.post("/upload")
@app.post("/api/scan")
async def upload_file(file: UploadFile = File(...)):
    contents = await file.read()
    size_kb = len(contents) // 1024
    logger.info(f"--- Upload --- file={file.filename!r} type={file.content_type} size={size_kb}KB")

    if not file.content_type.startswith(("image/", "application/pdf")):
        raise HTTPException(status_code=400, detail="Unsupported file type. Send an image or PDF.")

    if client is None or not _groq_api_key:
        raise HTTPException(
            status_code=503,
            detail="GROQ_API_KEY is not set. Add it in Render → Environment Variables."
        )

    try:
        data = None

        # ── STEP 1: Groq Vision API — PRIMARY for ALL document types ─────────
        if file.content_type == "application/pdf":
            logger.info("PDF: trying Groq Vision on page 1 first.")
            try:
                page_img = pdf_page_to_image(contents, page_num=0)
                data = extract_with_vision(page_img)
                if data and data.get("type") != "UNKNOWN":
                    logger.info("PDF: Groq Vision succeeded.")
                else:
                    logger.info("PDF: Groq Vision returned UNKNOWN — will try text fallback.")
                    data = None
            except Exception as e:
                logger.warning(f"PDF: Groq Vision step failed ({e}) — falling back to text.")
                data = None
        else:
            # Image — Vision is always tried first
            data = extract_with_vision(contents)

        # ── STEP 2: Text-layer + Groq LLM — for PDFs when Vision failed ──────
        if data is None and file.content_type == "application/pdf":
            logger.info("PDF: falling back to native text layer → Groq LLM.")
            raw_text = clean_ocr_text(extract_pdf_text(contents))
            logger.info(f"PDF text ({len(raw_text)} chars):\n{raw_text[:500]}")
            if raw_text.strip():
                data = llm_from_ocr_text(raw_text)

        # ── STEP 3: EasyOCR + Groq LLM — last resort for images ────────────
        if data is None or data.get("type") == "UNKNOWN":
            if file.content_type != "application/pdf":
                logger.info("Vision returned UNKNOWN/None — trying EasyOCR fallback.")
                raw_text = run_easy_ocr(contents)
                if raw_text.strip():
                    logger.info(f"EasyOCR Full Text: {raw_text}")
                    fallback = llm_from_ocr_text(raw_text)
                    if fallback:
                        has_data = any(
                            fallback.get(f, "-") not in ("-", "", None)
                            for f in ("name", "id_number", "dob", "location")
                        )
                        if has_data or data is None:
                            data = fallback
                            logger.info("Using EasyOCR+LLM result.")
                else:
                    logger.warning("EasyOCR extracted no text.")

        if not data:
            return empty_response(
                file.filename,
                f"All extraction methods failed [OCR Available: {ocr_available()}]. "
                f"Try a clearer image or check Render logs."
            )

        # Normalise keys for frontend
        data["address"] = data.get("location", "-")
        data["filename"] = file.filename

        # Regex boost: always run — recovers any missed numbers/dates/names
        combined = " ".join(str(v) for v in data.values())
        data = regex_boost(data, combined)
        data["document_type"] = data.get("type", "UNKNOWN")

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
