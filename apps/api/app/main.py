import logging
import os
import time
import uuid

import anyio.to_thread
from fastapi import FastAPI, File, Request, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import telemetry as tel
from .schemas import ExtractResponse
from .ocr import extract, AGREEMENT_FIELDS, MODEL_NAME, OCR_BACKEND, BadImageError, ModelOutputError, UpstreamError

log = logging.getLogger(__name__)

# Sync handlers run in this thread pool. Size it to the concurrency you expect
# to push to the model; vLLM batches whatever arrives concurrently.
THREADPOOL_SIZE = int(os.getenv("API_THREADPOOL_SIZE", "64"))

# Outcome -> HTTP status. 5xx outcomes count against the availability SLO.
_STATUS = {
    "upstream_timeout": 504,
    "upstream_rate_limited": 503,
    "upstream_error": 502,
    "model_output_error": 502,
}


async def _lifespan(app):
    anyio.to_thread.current_default_thread_limiter().total_tokens = THREADPOOL_SIZE
    yield


app = FastAPI(title="OCR Lab API", lifespan=_lifespan)
tel.setup(app)
tel.zero_counters(OCR_BACKEND, AGREEMENT_FIELDS)

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


@app.middleware("http")
async def request_id(request: Request, call_next):
    # nginx forwards its $request_id; generate one when called directly.
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex
    request.state.request_id = rid
    tel.trace.get_current_span().set_attribute("ocr.request_id", rid)
    response = await call_next(request)
    response.headers["x-request-id"] = rid
    return response


@app.get("/healthz")
def healthz():
    return {"ok": True}


# Plain `def`: FastAPI runs it in the thread pool, so a slow model call no
# longer blocks the event loop (and /healthz) for every other request.
@app.post("/extract", response_model=ExtractResponse)
def extract_passport(request: Request, file: UploadFile = File(...)):
    started = time.perf_counter()
    outcome = "ok"
    extra = {"request_id": request.state.request_id}
    try:
        if file.content_type not in {"image/png", "image/jpeg", "image/jpg"}:
            outcome = "bad_request"
            raise HTTPException(400, "unsupported content type")
        image_bytes = file.file.read()
        # Do NOT log image_bytes or extracted fields — PII.
        result = extract(image_bytes)
        extra["mrz_result"] = result.mrz_result
        return ExtractResponse(fields=result.fields, model=MODEL_NAME, mrz_result=result.mrz_result,
                               usage=result.usage)
    except BadImageError as e:
        outcome = "bad_request"
        raise HTTPException(400, str(e)) from None
    except UpstreamError as e:
        outcome = e.outcome
        raise HTTPException(_STATUS[outcome], str(e)) from e
    except ModelOutputError as e:
        outcome = "model_output_error"
        raise HTTPException(_STATUS[outcome], str(e)) from e
    except HTTPException:
        raise
    except Exception:
        outcome = "internal_error"
        log.exception("extract failed", extra=extra)
        raise HTTPException(500, "internal error")
    finally:
        elapsed = time.perf_counter() - started
        attrs = {"outcome": outcome, "backend": OCR_BACKEND}
        tel.extract_duration.record(elapsed, attrs)
        tel.extractions.add(1, attrs)
        tel.trace.get_current_span().set_attribute("ocr.outcome", outcome)
        extra["outcome"] = outcome
        log.info("extract done in %.3fs", elapsed, extra=extra)
