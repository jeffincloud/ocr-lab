import base64
import datetime as dt
import io
import json
import logging
import os
import re
from typing import Optional

import httpx
import ollama
from PIL import Image
from mrz.checker.td3 import TD3CodeChecker

from .schemas import PassportFields

log = logging.getLogger(__name__)

PROMPT = """You are an OCR system for passports. Extract the passport holder's data from the image.

Return ONLY a JSON object with these keys (use null if not visible):
- surname: family name as printed in the NAME/SURNAME field (NOT text from watermarks or the country header)
- given_names: first and middle names
- passport_number
- nationality
- date_of_birth (format: YYYY-MM-DD)
- sex (M or F)
- date_of_issue (format: YYYY-MM-DD)
- date_of_expiry (format: YYYY-MM-DD)
- issuing_authority
- mrz_line1
- mrz_line2

Ignore any watermarks, holograms, or specimen text. Return JSON only."""

OCR_BACKEND = os.getenv("OCR_BACKEND", "openai").lower()
MAX_IMAGE_DIM = int(os.getenv("MAX_IMAGE_DIM", "1024"))

# Ollama backend (local dev)
OLLAMA_MODEL = os.getenv("MODEL_NAME", "qwen3-vl:4b")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# OpenAI-compatible backend (cluster — vLLM serving Qwen3-VL via KServe)
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://qwen3-vl-4b-predictor.default.svc.cluster.local")
OPENAI_MODEL = os.getenv("OPENAI_MODEL_NAME", "qwen3-vl-4b")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "no-key")
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "60"))

MODEL_NAME = OLLAMA_MODEL if OCR_BACKEND == "ollama" else OPENAI_MODEL


def _resize(image_bytes: bytes) -> tuple[bytes, str]:
    img = Image.open(io.BytesIO(image_bytes))
    if max(img.size) <= MAX_IMAGE_DIM:
        return image_bytes, img.format or "PNG"
    img.thumbnail((MAX_IMAGE_DIM, MAX_IMAGE_DIM))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=95)
    return buf.getvalue(), "JPEG"


def _normalize_mrz_line(line: str) -> str:
    s = (line or "").strip().upper()
    if len(s) > 44:
        return s[:44]
    return s.ljust(44, "<")


def _expand_year(yy: str, kind: str) -> str:
    if kind == "dob":
        return f"19{yy}" if int(yy) > (dt.date.today().year % 100) else f"20{yy}"
    return f"20{yy}"


def _yymmdd_to_iso(s: str, kind: str) -> Optional[str]:
    if not s or len(s) != 6 or not s.isdigit():
        return None
    return f"{_expand_year(s[:2], kind)}-{s[2:4]}-{s[4:6]}"


def _merge_mrz(fields: PassportFields) -> PassportFields:
    """Override deterministic fields with MRZ-parsed values if check digits validate.

    MRZ covers: surname, given_names, passport_number, nationality,
    date_of_birth, sex, date_of_expiry. Falls back to VLM values on any parse
    or check-digit failure. Never touches date_of_issue / issuing_authority
    (those aren't encoded in the MRZ).
    """
    if not fields.mrz_line1 or not fields.mrz_line2:
        return fields
    l1 = _normalize_mrz_line(fields.mrz_line1)
    l2 = _normalize_mrz_line(fields.mrz_line2)
    try:
        check = TD3CodeChecker(f"{l1}\n{l2}")
    except Exception as e:
        log.info("mrz parse failed (%s); keeping VLM values", e.__class__.__name__)
        return fields
    if not bool(check):
        log.info("mrz check digits invalid; keeping VLM values")
        return fields
    f = check.fields()
    log.info("mrz parse ok; overriding VLM fields from MRZ")
    return fields.model_copy(update={
        "surname": f.surname,
        "given_names": f.name,
        "passport_number": f.document_number,
        "nationality": f.nationality,
        "date_of_birth": _yymmdd_to_iso(f.birth_date, "dob"),
        "sex": f.sex,
        "date_of_expiry": _yymmdd_to_iso(f.expiry_date, "future"),
    })


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_fences(s: str) -> str:
    return _FENCE_RE.sub("", s).strip()


def _extract_ollama(image_bytes: bytes) -> str:
    client = ollama.Client(host=OLLAMA_HOST)
    r = client.generate(
        model=OLLAMA_MODEL,
        prompt=PROMPT,
        images=[image_bytes],
        format="json",
        think=False,
        options={"temperature": 0, "num_predict": 1024},
    )
    payload = r.get("response") or r.get("thinking") or ""
    if not payload:
        log.warning("empty ollama response | done_reason=%s", r.get("done_reason"))
        raise ValueError("model returned empty response")
    return payload


def _extract_openai(image_bytes: bytes, image_format: str) -> str:
    mime = "image/jpeg" if image_format.upper() == "JPEG" else "image/png"
    data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
    body = {
        "model": OPENAI_MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": PROMPT},
            ],
        }],
        "max_tokens": 1024,
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    r = httpx.post(
        f"{OPENAI_BASE_URL.rstrip('/')}/v1/chat/completions",
        json=body,
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
        timeout=OPENAI_TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    content = data["choices"][0]["message"]["content"] or ""
    if not content:
        raise ValueError("model returned empty response")
    return _strip_fences(content)


def extract(image_bytes: bytes) -> PassportFields:
    resized, img_format = _resize(image_bytes)
    if OCR_BACKEND == "ollama":
        payload = _extract_ollama(resized)
    else:
        payload = _extract_openai(resized, img_format)
    fields = PassportFields(**json.loads(payload))
    return _merge_mrz(fields)
