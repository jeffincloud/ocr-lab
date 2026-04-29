import os

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .schemas import ExtractResponse
from .ocr import extract, MODEL_NAME

app = FastAPI(title="OCR Lab API")

# CORS is opt-in via env var. Unset in cluster (frontend proxies /api via nginx);
# set to e.g. "http://localhost:3000" during local dev.
_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_methods=["POST", "GET", "OPTIONS"],
        allow_headers=["*"],
    )


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/extract", response_model=ExtractResponse)
async def extract_passport(file: UploadFile = File(...)):
    if file.content_type not in {"image/png", "image/jpeg", "image/jpg"}:
        raise HTTPException(400, "unsupported content type")
    image_bytes = await file.read()
    # Do NOT log image_bytes — PII.
    fields = extract(image_bytes)
    return ExtractResponse(fields=fields, model=MODEL_NAME)
