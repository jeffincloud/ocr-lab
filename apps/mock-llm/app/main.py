"""A fake vLLM: OpenAI-compatible chat completions with simulated engine behaviour.

Lets the whole stack (API, gateway, telemetry, dashboards, SLOs, load tests)
run on a laptop or CPU-only cluster. It is not a model. It:

- reads the ground truth that tools/passport-gen embeds in each PNG (tEXt
  chunk "ocr_truth") and answers with it, optionally corrupted at a set rate;
- simulates queueing (max_num_seqs), prefill cost proportional to image
  tokens, and decode cost per output token that grows with batch size;
- exposes a subset of vLLM's Prometheus metrics with the same names, so the
  dashboards and recording rules work unchanged against the real engine;
- continues the caller's trace (W3C traceparent) with an `llm_request` span.

Numbers are illustrative only. Never present mock results as GPU results.
"""
import asyncio
import base64
import io
import json
import math
import os
import random
import time
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from PIL import Image
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

MODEL = os.getenv("MOCK_MODEL_NAME", "qwen3-5-9b")
MAX_NUM_SEQS = int(os.getenv("MOCK_MAX_NUM_SEQS", "16"))
PREFILL_MS_PER_TOKEN = float(os.getenv("MOCK_PREFILL_MS_PER_TOKEN", "0.35"))
DECODE_MS_PER_TOKEN = float(os.getenv("MOCK_DECODE_MS_PER_TOKEN", "14"))
BATCH_SLOWDOWN = float(os.getenv("MOCK_BATCH_SLOWDOWN", "0.04"))  # per running seq
KV_CAPACITY_TOKENS = int(os.getenv("MOCK_KV_CAPACITY_TOKENS", "60000"))
STARTUP_SECONDS = float(os.getenv("MOCK_STARTUP_SECONDS", "0"))
FIELD_ERROR_RATE = float(os.getenv("MOCK_FIELD_ERROR_RATE", "0.03"))
MRZ_ERROR_RATE = float(os.getenv("MOCK_MRZ_ERROR_RATE", "0.01"))
JSON_ERROR_RATE = float(os.getenv("MOCK_JSON_ERROR_RATE", "0.005"))
PATCH_PX = 32  # Qwen3.5 (as Qwen3-VL): 16 px patches merged 2x2 -> one token per 32x32 px
TEXT_PROMPT_TOKENS = 260

L = ["model_name"]
B_LAT = [0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 1, 2.5, 5, 7.5, 10, 20, 40, 80]
m_running = Gauge("vllm:num_requests_running", "Requests in the running batch", L)
m_waiting = Gauge("vllm:num_requests_waiting", "Requests waiting to be scheduled", L)
m_kv = Gauge("vllm:kv_cache_usage_perc", "KV cache usage (1 = 100%)", L)
m_prompt = Counter("vllm:prompt_tokens", "Prefill tokens processed", L)
m_gen = Counter("vllm:generation_tokens", "Generation tokens processed", L)
m_success = Counter("vllm:request_success", "Finished requests", L + ["finished_reason"])
m_ttft = Histogram("vllm:time_to_first_token_seconds", "TTFT", L, buckets=B_LAT)
m_itl = Histogram("vllm:inter_token_latency_seconds", "Inter-token latency", L,
                  buckets=[0.005, 0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.075, 0.1, 0.25])
m_e2e = Histogram("vllm:e2e_request_latency_seconds", "E2E request latency", L, buckets=B_LAT)
m_queue = Histogram("vllm:request_queue_time_seconds", "Time waiting in queue", L, buckets=B_LAT)
m_prefill = Histogram("vllm:request_prefill_time_seconds", "Prefill phase time", L, buckets=B_LAT)
m_decode = Histogram("vllm:request_decode_time_seconds", "Decode phase time", L, buckets=B_LAT)
m_req_prompt = Histogram("vllm:request_prompt_tokens", "Prompt tokens per request", L,
                         buckets=[64, 128, 256, 512, 1024, 2048, 4096, 8192])
m_req_gen = Histogram("vllm:request_generation_tokens", "Generation tokens per request", L,
                      buckets=[16, 32, 64, 128, 256, 512, 1024])
# The llm-d endpoint picker reads this to size its prefix-cache index.
Gauge("vllm:cache_config_info", "KV cache config", ["block_size", "num_gpu_blocks"]).labels(
    "16", str(KV_CAPACITY_TOKENS // 16)).set(1)

app = FastAPI(title="mock-llm")


# KServe serves each LLMInferenceService under /<namespace>/<name>/ on the
# gateway; depending on the version the route may or may not strip it. Accept
# both, like vLLM does with --root-path.
@app.middleware("http")
async def _strip_root_path(request: Request, call_next):
    path = request.scope["path"]
    for marker in ("/v1/", "/health", "/metrics"):
        i = path.find(marker)
        if i > 0:
            request.scope["path"] = path[i:]
            break
    return await call_next(request)
_started = time.monotonic()
_slots = asyncio.Semaphore(MAX_NUM_SEQS)
_state = {"running": 0, "waiting": 0, "kv_tokens": 0}

_tracer = None
if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

    _tp = TracerProvider(resource=Resource.create({"service.name": os.getenv("OTEL_SERVICE_NAME", "mock-llm")}))
    _tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    _tracer = _tp.get_tracer("mock-llm")
    _propagator = TraceContextTextMapPropagator()


def _set_gauges():
    m_running.labels(MODEL).set(_state["running"])
    m_waiting.labels(MODEL).set(_state["waiting"])
    m_kv.labels(MODEL).set(min(1.0, _state["kv_tokens"] / KV_CAPACITY_TOKENS))


_set_gauges()  # export zeros before the first request, as vLLM does


def _ready() -> bool:
    return time.monotonic() - _started >= STARTUP_SECONDS


def _decode_image(messages) -> tuple[int, dict | None]:
    """Return (image tokens, embedded ground truth or None)."""
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if part.get("type") != "image_url":
                continue
            url = part["image_url"]["url"]
            raw = base64.b64decode(url.split(",", 1)[1])
            img = Image.open(io.BytesIO(raw))
            tokens = math.ceil(img.width / PATCH_PX) * math.ceil(img.height / PATCH_PX)
            truth = img.info.get("ocr_truth")
            return tokens, json.loads(truth) if truth else None
    return 0, None


def _corrupt_char(s: str) -> str:
    if not s:
        return s
    i = random.randrange(len(s))
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return s[:i] + random.choice(alphabet.replace(s[i], "")) + s[i + 1:]


def _answer(truth: dict | None) -> str:
    if random.random() < JSON_ERROR_RATE:
        return '{"surname": "TRUNCATED'
    if truth is None:
        truth = {"surname": "UNKNOWN", "given_names": None, "passport_number": None, "mrz_line1": None,
                 "mrz_line2": None}
    out = dict(truth)
    for key in ("surname", "given_names", "passport_number", "issuing_authority"):
        if out.get(key) and random.random() < FIELD_ERROR_RATE:
            out[key] = _corrupt_char(out[key])
    if out.get("mrz_line2") and random.random() < MRZ_ERROR_RATE:
        out["mrz_line2"] = _corrupt_char(out["mrz_line2"])
    return json.dumps(out)


async def _run(body: dict, headers):
    """Simulate one request through queue, prefill and decode; yield text pieces."""
    image_tokens, truth = _decode_image(body.get("messages", []))
    prompt_tokens = image_tokens + TEXT_PROMPT_TOKENS
    text = _answer(truth)
    pieces = [text[i:i + 4] for i in range(0, len(text), 4)]  # ~4 chars per token
    t0 = time.monotonic()
    _state["waiting"] += 1
    _set_gauges()
    async with _slots:
        _state["waiting"] -= 1
        _state["running"] += 1
        _state["kv_tokens"] += prompt_tokens
        _set_gauges()
        t_sched = time.monotonic()
        try:
            await asyncio.sleep(prompt_tokens * PREFILL_MS_PER_TOKEN / 1000 * (1 + BATCH_SLOWDOWN * _state["running"]))
            t_first = time.monotonic()
            yield {"first": True}
            last = t_first
            for p in pieces:
                yield p
                await asyncio.sleep(DECODE_MS_PER_TOKEN / 1000 * (1 + BATCH_SLOWDOWN * _state["running"]))
                now = time.monotonic()
                m_itl.labels(MODEL).observe(now - last)
                last = now
                _state["kv_tokens"] += 1
        finally:
            _state["running"] -= 1
            _state["kv_tokens"] -= prompt_tokens + len(pieces)
            _set_gauges()
    t_end = time.monotonic()
    m_queue.labels(MODEL).observe(t_sched - t0)
    m_prefill.labels(MODEL).observe(t_first - t_sched)
    m_decode.labels(MODEL).observe(t_end - t_first)
    m_ttft.labels(MODEL).observe(t_first - t0)
    m_e2e.labels(MODEL).observe(t_end - t0)
    m_prompt.labels(MODEL).inc(prompt_tokens)
    m_gen.labels(MODEL).inc(len(pieces))
    m_req_prompt.labels(MODEL).observe(prompt_tokens)
    m_req_gen.labels(MODEL).observe(len(pieces))
    m_success.labels(MODEL, "stop").inc()
    yield {"usage": {"prompt_tokens": prompt_tokens, "completion_tokens": len(pieces)},
           "timing": {"queue": t_sched - t0, "ttft": t_first - t0, "e2e": t_end - t0}}


def _span(request: Request):
    if _tracer is None:
        return None
    ctx = _propagator.extract(dict(request.headers))
    return _tracer.start_span("llm_request", context=ctx, kind=trace.SpanKind.SERVER,
                              attributes={"gen_ai.request.model": MODEL})


def _finish_span(span, final: dict):
    if span is None:
        return
    span.set_attributes({
        "gen_ai.usage.input_tokens": final["usage"]["prompt_tokens"],
        "gen_ai.usage.output_tokens": final["usage"]["completion_tokens"],
        "gen_ai.latency.time_in_queue": final["timing"]["queue"],
        "gen_ai.latency.time_to_first_token": final["timing"]["ttft"],
        "gen_ai.latency.e2e": final["timing"]["e2e"],
    })
    span.end()


@app.post("/v1/chat/completions")
async def chat(request: Request):
    if not _ready():
        return JSONResponse({"error": "model loading"}, status_code=503)
    body = await request.json()
    rid = f"chatcmpl-{uuid.uuid4().hex[:16]}"
    span = _span(request)

    if body.get("stream"):
        async def sse():
            final = None
            async for item in _run(body, request.headers):
                if isinstance(item, dict):
                    final = item if "usage" in item else None
                    continue
                chunk = {"id": rid, "object": "chat.completion.chunk", "model": MODEL,
                         "choices": [{"index": 0, "delta": {"content": item}, "finish_reason": None}]}
                yield f"data: {json.dumps(chunk)}\n\n"
            done = {"id": rid, "object": "chat.completion.chunk", "model": MODEL,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            yield f"data: {json.dumps(done)}\n\n"
            if (body.get("stream_options") or {}).get("include_usage"):
                yield f"data: {json.dumps({'id': rid, 'choices': [], 'usage': final['usage']})}\n\n"
            yield "data: [DONE]\n\n"
            _finish_span(span, final)
        return StreamingResponse(sse(), media_type="text/event-stream")

    parts, final = [], None
    async for item in _run(body, request.headers):
        if isinstance(item, dict):
            final = item if "usage" in item else None
        else:
            parts.append(item)
    _finish_span(span, final)
    return {"id": rid, "object": "chat.completion", "model": MODEL,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "".join(parts)},
                         "finish_reason": "stop"}],
            "usage": {**final["usage"], "total_tokens": sum(final["usage"].values())}}


@app.get("/v1/models")
def models():
    return {"object": "list", "data": [{"id": MODEL, "object": "model"}]}


@app.get("/health")
def health():
    return Response(status_code=200 if _ready() else 503)


@app.get("/metrics")
def prom():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
