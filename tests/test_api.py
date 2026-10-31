"""API behaviour under concurrency, error mapping, and the telemetry it emits.

Run from the repo root:
    ../.venv/bin/python -m pytest tests -v
"""
import io
import json
import sys
import pathlib
import threading
import time

import httpx
import pytest
from PIL import Image
from opentelemetry import metrics, trace
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "apps" / "api"))

SPANS = InMemorySpanExporter()
READER = InMemoryMetricReader()
_tp = TracerProvider()
_tp.add_span_processor(SimpleSpanProcessor(SPANS))
trace.set_tracer_provider(_tp)
metrics.set_meter_provider(MeterProvider(metric_readers=[READER]))

from fastapi.testclient import TestClient  # noqa: E402

from app import main, ocr  # noqa: E402

VALID_MRZ_L1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
VALID_MRZ_L2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"
ANSWER = {"surname": "ERIKSSON", "given_names": "ANNA MARIA", "passport_number": "L898902C3",
          "nationality": "UTO", "date_of_birth": "1974-08-12", "sex": "F",
          "date_of_expiry": "2012-04-15", "mrz_line1": VALID_MRZ_L1, "mrz_line2": VALID_MRZ_L2}


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 40), "white").save(buf, format="PNG")
    return buf.getvalue()


def _sse(content: str) -> bytes:
    chunks = [{"id": "cmpl-1", "choices": [{"delta": {"content": content[:10]}}]},
              {"id": "cmpl-1", "choices": [{"delta": {"content": content[10:]}, "finish_reason": "stop"}]},
              {"id": "cmpl-1", "choices": [], "usage": {"prompt_tokens": 900, "completion_tokens": 120}}]
    return b"".join(f"data: {json.dumps(c)}\n\n".encode() for c in chunks) + b"data: [DONE]\n\n"


def _use(handler):
    ocr._client = httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def client():
    SPANS.clear()
    with TestClient(main.app) as c:
        yield c


def _post(c):
    return c.post("/extract", files={"file": ("p.png", _png(), "image/png")})


def test_requests_run_concurrently(client):
    # The original async handler called a blocking client and served one
    # request at a time. 8 requests x 0.5 s must now overlap.
    def slow(request):
        time.sleep(0.5)
        return httpx.Response(200, content=_sse(json.dumps(ANSWER)))
    _use(slow)
    results = []
    threads = [threading.Thread(target=lambda: results.append(_post(client).status_code)) for _ in range(8)]
    t0 = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert results == [200] * 8
    assert time.perf_counter() - t0 < 2.0


def test_healthz_not_blocked_by_inference(client):
    _use(lambda r: (time.sleep(1.5), httpx.Response(200, content=_sse(json.dumps(ANSWER))))[1])
    t = threading.Thread(target=lambda: _post(client))
    t.start()
    time.sleep(0.2)
    t0 = time.perf_counter()
    assert client.get("/healthz").status_code == 200
    assert time.perf_counter() - t0 < 0.5
    t.join()


def test_success_returns_usage_mrz_and_genai_span(client):
    _use(lambda r: httpx.Response(200, content=_sse(json.dumps(ANSWER)),
                                  headers={"x-ratelimit-remaining-requests": "42"}))
    r = _post(client)
    assert r.status_code == 200
    body = r.json()
    assert body["mrz_result"] == "valid"
    assert body["usage"] == {"input_tokens": 900, "output_tokens": 120}
    assert r.headers["x-request-id"]
    spans = {s.name: s for s in SPANS.get_finished_spans()}
    chat = spans["chat qwen3-5-9b"]
    assert chat.attributes["gen_ai.usage.input_tokens"] == 900
    assert chat.attributes["gen_ai.usage.output_tokens"] == 120
    assert chat.attributes["ocr.upstream.ratelimit.remaining.requests"] == 42
    assert "ocr.upstream.time_to_first_token" in chat.attributes
    assert {"ocr.preprocess", "ocr.inference", "ocr.parse", "ocr.mrz"} <= spans.keys()
    # PII guard: no extracted values anywhere on spans.
    for s in SPANS.get_finished_spans():
        assert "ERIKSSON" not in json.dumps(dict(s.attributes or {}))


@pytest.mark.parametrize("handler,status,outcome", [
    (lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow")), 504, "upstream_timeout"),
    (lambda r: httpx.Response(429), 503, "upstream_rate_limited"),
    (lambda r: httpx.Response(500), 502, "upstream_error"),
    (lambda r: httpx.Response(200, content=_sse("not json at all, sorry")), 502, "model_output_error"),
])
def test_upstream_failures_map_to_explicit_statuses(client, handler, status, outcome):
    _use(handler)
    assert _post(client).status_code == status
    data = READER.get_metrics_data()
    seen = {
        dp.attributes["outcome"]
        for rm in data.resource_metrics for sm in rm.scope_metrics for m in sm.metrics
        if m.name == "ocr.extractions" for dp in m.data.data_points if dp.value > 0
    }
    assert outcome in seen


def test_counters_start_at_zero():
    # A series that first appears at 1 is invisible to rate(), so the first error of
    # each kind after a restart would never reach the SLOs.
    data = READER.get_metrics_data()
    names = {m.name: {tuple(sorted(dp.attributes.items())) for dp in m.data.data_points}
             for rm in data.resource_metrics for sm in rm.scope_metrics for m in sm.metrics}
    assert (("backend", ocr.OCR_BACKEND), ("outcome", "internal_error")) in names["ocr.extractions"]
    assert (("result", "unparseable"),) in names["ocr.mrz.checks"]
    assert (("agree", "false"), ("field", "surname")) in names["ocr.mrz.field_agreement"]


def test_bad_content_type_is_400(client):
    r = client.post("/extract", files={"file": ("p.gif", b"GIF89a", "image/gif")})
    assert r.status_code == 400


def test_corrupt_image_is_400_not_500(client):
    # A bad upload is the client's error and must not burn the availability SLO.
    r = client.post("/extract", files={"file": ("p.png", b"not an image", "image/png")})
    assert r.status_code == 400


def test_extra_body_reaches_the_engine(client, monkeypatch):
    # Qwen3.5 thinks unless told not to; the switch rides in OPENAI_EXTRA_BODY.
    monkeypatch.setattr(ocr, "OPENAI_EXTRA_BODY", {"chat_template_kwargs": {"enable_thinking": False}})
    seen = {}

    def capture(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, content=_sse(json.dumps(ANSWER)))
    _use(capture)
    assert _post(client).status_code == 200
    assert seen["chat_template_kwargs"] == {"enable_thinking": False}
    assert seen["response_format"] == {"type": "json_object"}
