import base64
import datetime as dt
import io
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional

import httpx
import ollama
from opentelemetry.trace import SpanKind, Status, StatusCode
from PIL import Image
from mrz.checker.td3 import TD3CodeChecker

from . import telemetry as tel
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

# OpenAI-compatible backend (cluster — vLLM serving Qwen3.5 via KServe + llm-d, or a
# hosted provider's OpenAI-compatible endpoint for the closed-API comparison)
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "http://kserve-ingress-gateway-istio.kserve.svc.cluster.local/default/qwen3-5-9b")
OPENAI_MODEL = os.getenv("OPENAI_MODEL_NAME", "qwen3-5-9b")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "no-key")
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "60"))
# Streaming lets the API measure time-to-first-token on the client side, which
# is the only TTFT you get from a closed API.
OPENAI_STREAM = os.getenv("OPENAI_STREAM", "true").lower() == "true"
# Put the static prompt before the image so requests share a longer prefix
# (prefix-cache experiment). Default keeps the original image-first order.
PROMPT_FIRST = os.getenv("PROMPT_FIRST", "false").lower() == "true"
# Label for gen_ai.provider.name: "vllm" when self-hosted, e.g. "openai" for a hosted API.
PROVIDER_NAME = os.getenv("GENAI_PROVIDER_NAME", "vllm")
MAX_CONNECTIONS = int(os.getenv("UPSTREAM_MAX_CONNECTIONS", "64"))
# KServe's LLMInferenceService gateway route may use a self-signed certificate.
OPENAI_TLS_VERIFY = os.getenv("OPENAI_TLS_VERIFY", "true").lower() == "true"
# Extra JSON merged into every chat request, for engine-specific knobs a hosted
# API would reject, e.g. {"chat_template_kwargs": {"enable_thinking": true}}.
OPENAI_EXTRA_BODY = json.loads(os.getenv("OPENAI_EXTRA_BODY") or "{}")
# Reasoning tokens count against this, so a thinking model needs room for both
# its reasoning and the JSON, or the answer is cut off.
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "1024"))

MODEL_NAME = OLLAMA_MODEL if OCR_BACKEND == "ollama" else OPENAI_MODEL

# One pooled client per process. A new client per request would pay a TCP
# handshake each time and hide connection reuse from the network dashboards.
_client = httpx.Client(
    timeout=httpx.Timeout(OPENAI_TIMEOUT, connect=5.0),
    verify=OPENAI_TLS_VERIFY,
    limits=httpx.Limits(max_connections=MAX_CONNECTIONS, max_keepalive_connections=MAX_CONNECTIONS),
)

# Rate-limit headers from common providers, mapped to a small fixed label set.
_RATELIMIT_HEADERS = {
    "x-ratelimit-remaining-requests": "requests",
    "x-ratelimit-remaining-tokens": "tokens",
    "anthropic-ratelimit-requests-remaining": "requests",
    "anthropic-ratelimit-input-tokens-remaining": "input_tokens",
    "anthropic-ratelimit-output-tokens-remaining": "output_tokens",
}


class UpstreamError(Exception):
    """The model endpoint failed. `outcome` is the label used on metrics."""

    def __init__(self, outcome: str, detail: str):
        super().__init__(detail)
        self.outcome = outcome


class ModelOutputError(Exception):
    """The model answered, but not with parseable JSON in the expected shape."""


class BadImageError(Exception):
    """The upload could not be decoded as an image: the client's error, not ours."""


@dataclass
class Completion:
    content: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    response_id: Optional[str] = None
    finish_reason: Optional[str] = None
    ttft: Optional[float] = None


@dataclass
class ExtractResult:
    fields: PassportFields
    mrz_result: str
    usage: dict = field(default_factory=dict)


def _resize(image_bytes: bytes) -> tuple[bytes, str]:
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as e:
        raise BadImageError(f"not a readable image ({e.__class__.__name__})") from None
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


def _check_mrz(fields: PassportFields) -> tuple[PassportFields, str]:
    """Override fields with MRZ-parsed values if check digits validate.

    Overrides passport_number, nationality, date_of_birth, sex and date_of_expiry.
    Names are only filled in when the VLM has none: TD3 check digits don't cover
    them, so a valid MRZ can still carry a misread name (OAKAFOR for OKAFOR) that
    would replace a correct reading of the printed page. Falls back to VLM values
    on any parse or check-digit failure. Never touches date_of_issue /
    issuing_authority (those aren't encoded in the MRZ).

    Returns the merged fields and the check result: valid, invalid, missing or
    unparseable. The result is the label-free quality signal behind the
    MRZ-validity SLI.
    """
    if not fields.mrz_line1 or not fields.mrz_line2:
        return fields, "missing"
    l1 = _normalize_mrz_line(fields.mrz_line1)
    l2 = _normalize_mrz_line(fields.mrz_line2)
    try:
        check = TD3CodeChecker(f"{l1}\n{l2}")
    except Exception as e:
        log.info("mrz parse failed (%s); keeping VLM values", e.__class__.__name__)
        return fields, "unparseable"
    if not bool(check):
        log.info("mrz check digits invalid; keeping VLM values")
        return fields, "invalid"
    f = check.fields()
    log.info("mrz parse ok; overriding VLM fields from MRZ")
    mrz = fields.model_copy(update={
        "surname": f.surname,
        "given_names": f.name,
        "passport_number": f.document_number,
        "nationality": f.nationality,
        "date_of_birth": _yymmdd_to_iso(f.birth_date, "dob"),
        "sex": f.sex,
        "date_of_expiry": _yymmdd_to_iso(f.expiry_date, "future"),
    })
    _record_field_agreement(fields, mrz)
    return mrz.model_copy(update={"surname": fields.surname or mrz.surname,
                                  "given_names": fields.given_names or mrz.given_names}), "valid"


def _merge_mrz(fields: PassportFields) -> PassportFields:
    return _check_mrz(fields)[0]


def _norm(v: Optional[str]) -> str:
    return re.sub(r"[^A-Z0-9]", "", (v or "").upper())


def _record_field_agreement(vlm: PassportFields, mrz: PassportFields) -> None:
    """Count, per field, whether what the VLM read from the printed page matches
    the check-digit-validated MRZ. A drop here means the model's visual reading
    got worse even when the MRZ still rescues the final answer. Not nationality:
    the page prints COLOMBIA and the MRZ says COL, so it never matches."""
    for name in ("surname", "given_names", "passport_number",
                 "date_of_birth", "sex", "date_of_expiry"):
        agree = _norm(getattr(vlm, name)) == _norm(getattr(mrz, name))
        tel.field_agreement.add(1, {"field": name, "agree": str(agree).lower()})


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _strip_fences(s: str) -> str:
    return _FENCE_RE.sub("", s).strip()


def _extract_ollama(image_bytes: bytes) -> Completion:
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
        raise ModelOutputError("model returned empty response")
    return Completion(payload, r.get("prompt_eval_count"), r.get("eval_count"),
                      finish_reason=r.get("done_reason"))


def _record_ratelimits(headers: httpx.Headers) -> dict:
    seen = {}
    for header, kind in _RATELIMIT_HEADERS.items():
        value = headers.get(header)
        if value is not None and value.isdigit():
            tel.ratelimit_remaining.set(int(value), {"limit": kind})
            seen[f"ocr.upstream.ratelimit.remaining.{kind}"] = int(value)
    return seen


def _read_stream(r: httpx.Response, started: float) -> Completion:
    """Consume an OpenAI-style SSE stream, timing the first content token."""
    parts, comp = [], Completion("")
    for line in r.iter_lines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        chunk = json.loads(data)
        comp.response_id = comp.response_id or chunk.get("id")
        for choice in chunk.get("choices") or []:
            delta = (choice.get("delta") or {}).get("content")
            if delta:
                if comp.ttft is None:
                    comp.ttft = time.perf_counter() - started
                parts.append(delta)
            if choice.get("finish_reason"):
                comp.finish_reason = choice["finish_reason"]
        usage = chunk.get("usage")
        if usage:
            comp.input_tokens = usage.get("prompt_tokens")
            comp.output_tokens = usage.get("completion_tokens")
    comp.content = "".join(parts)
    return comp


def _extract_openai(image_bytes: bytes, image_format: str) -> Completion:
    mime = "image/jpeg" if image_format.upper() == "JPEG" else "image/png"
    data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
    image_part = {"type": "image_url", "image_url": {"url": data_url}}
    text_part = {"type": "text", "text": PROMPT}
    body = {
        "model": OPENAI_MODEL,
        "messages": [{
            "role": "user",
            "content": [text_part, image_part] if PROMPT_FIRST else [image_part, text_part],
        }],
        "max_tokens": OPENAI_MAX_TOKENS,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        **OPENAI_EXTRA_BODY,
    }
    if OPENAI_STREAM:
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}

    started = time.perf_counter()
    url = f"{OPENAI_BASE_URL.rstrip('/')}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
    try:
        with _client.stream("POST", url, json=body, headers=headers) as r:
            attrs = _record_ratelimits(r.headers)
            upstream_id = r.headers.get("x-request-id") or r.headers.get("request-id")
            if r.status_code == 429:
                raise UpstreamError("upstream_rate_limited", "model endpoint rate limited the request")
            if r.status_code >= 400:
                r.read()
                raise UpstreamError("upstream_error", f"model endpoint returned {r.status_code}")
            if OPENAI_STREAM:
                comp = _read_stream(r, started)
            else:
                data = json.loads(r.read())
                choice = data["choices"][0]
                usage = data.get("usage") or {}
                comp = Completion(choice["message"]["content"] or "", usage.get("prompt_tokens"),
                                  usage.get("completion_tokens"), data.get("id"), choice.get("finish_reason"))
    except httpx.TimeoutException as e:
        raise UpstreamError("upstream_timeout", f"model endpoint timed out ({e.__class__.__name__})") from e
    except httpx.TransportError as e:
        raise UpstreamError("upstream_error", f"model endpoint unreachable ({e.__class__.__name__})") from e

    span = tel.trace.get_current_span()
    span.set_attributes(attrs)
    if upstream_id:
        span.set_attribute("ocr.upstream.request_id", upstream_id)
    if comp.ttft is not None:
        tel.upstream_ttft.record(comp.ttft, {"gen_ai.request.model": OPENAI_MODEL})
    if not comp.content:
        raise ModelOutputError("model returned empty response")
    comp.content = _strip_fences(comp.content)
    return comp


def _infer(image_bytes: bytes, image_format: str) -> Completion:
    """Call the model inside a GenAI client span (semconv: "{operation} {model}")."""
    common = {"gen_ai.operation.name": "chat", "gen_ai.provider.name": PROVIDER_NAME,
              "gen_ai.request.model": MODEL_NAME}
    with tel.tracer.start_as_current_span(f"chat {MODEL_NAME}", kind=SpanKind.CLIENT) as span:
        max_tokens = 1024 if OCR_BACKEND == "ollama" else OPENAI_MAX_TOKENS
        span.set_attributes({**common, "gen_ai.request.max_tokens": max_tokens, "gen_ai.request.temperature": 0,
                             "gen_ai.output.type": "json"})
        started = time.perf_counter()
        error_type = None
        try:
            if OCR_BACKEND == "ollama":
                comp = _extract_ollama(image_bytes)
            else:
                comp = _extract_openai(image_bytes, image_format)
            return comp
        except UpstreamError as e:
            error_type = e.outcome
            raise
        except Exception as e:
            error_type = e.__class__.__name__
            raise
        finally:
            elapsed = time.perf_counter() - started
            tel.genai_duration.record(elapsed, {**common, **({"error.type": error_type} if error_type else {})})
            if error_type is None:
                if comp.response_id:
                    span.set_attribute("gen_ai.response.id", comp.response_id)
                if comp.finish_reason:
                    span.set_attribute("gen_ai.response.finish_reasons", [comp.finish_reason])
                for kind, n in (("input", comp.input_tokens), ("output", comp.output_tokens)):
                    if n is not None:
                        span.set_attribute(f"gen_ai.usage.{kind}_tokens", n)
                        tel.genai_tokens.record(n, {**common, "gen_ai.token.type": kind})
                if comp.ttft is not None:
                    span.set_attribute("ocr.upstream.time_to_first_token", round(comp.ttft, 4))
            else:
                span.set_attribute("error.type", error_type)
                span.set_status(Status(StatusCode.ERROR, error_type))


class _stage:
    """Time a pipeline stage as both a span and a histogram sample."""

    def __init__(self, name: str):
        self.name = name

    def __enter__(self):
        self._cm = tel.tracer.start_as_current_span(f"ocr.{self.name}")
        self.span = self._cm.__enter__()
        self._t0 = time.perf_counter()
        return self.span

    def __exit__(self, *exc):
        tel.stage_duration.record(time.perf_counter() - self._t0, {"stage": self.name})
        return self._cm.__exit__(*exc)


def extract(image_bytes: bytes) -> ExtractResult:
    with _stage("preprocess") as span:
        resized, img_format = _resize(image_bytes)
        span.set_attributes({"ocr.image.input_bytes": len(image_bytes), "ocr.image.sent_bytes": len(resized),
                             "ocr.image.format": img_format})
        tel.image_size.record(len(resized), {"format": img_format})
    with _stage("inference"):
        comp = _infer(resized, img_format)
    with _stage("parse"):
        try:
            fields = PassportFields(**json.loads(comp.content))
        except (ValueError, TypeError) as e:
            # `from None`: pydantic's error text echoes the input values (passport
            # data), and a chained cause would land in the span's stack trace.
            raise ModelOutputError(f"model output is not valid passport JSON ({e.__class__.__name__})") from None
    with _stage("mrz") as span:
        fields, mrz_result = _check_mrz(fields)
        span.set_attribute("ocr.mrz.result", mrz_result)
        tel.mrz_checks.add(1, {"result": mrz_result})
    usage = {"input_tokens": comp.input_tokens, "output_tokens": comp.output_tokens}
    return ExtractResult(fields, mrz_result, usage)
