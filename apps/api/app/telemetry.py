"""OpenTelemetry setup: traces, metrics (with exemplars) and logs over OTLP.

Telemetry is exported only when OTEL_EXPORTER_OTLP_ENDPOINT is set. Without it
the API still runs; the instruments below fall back to the no-op providers.
Stdout logs are always JSON with trace_id/span_id so `kubectl logs` lines can
be matched to traces even without a collector.

PII rule: nothing in this module (or in callers) may put image bytes, prompts,
model output or extracted passport fields on spans, metrics or logs.
"""
import json
import logging
import os
import sys

from opentelemetry import metrics, trace

log = logging.getLogger(__name__)

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "ocr-api")

# Seconds. Covers a 50 ms cache hit up to the 60 s upstream timeout.
LATENCY_BUCKETS = [0.05, 0.1, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 5, 6, 8, 10, 15, 20, 30, 45, 60, 90]
TOKEN_BUCKETS = [16, 32, 64, 128, 256, 512, 768, 1024, 1536, 2048, 4096, 8192]
BYTES_BUCKETS = [16_384, 65_536, 131_072, 262_144, 524_288, 1_048_576, 2_097_152, 4_194_304, 8_388_608]

_enabled = False


def enabled() -> bool:
    return _enabled


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with the active trace context injected."""

    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        ctx = trace.get_current_span().get_span_context()
        if ctx.is_valid:
            out["trace_id"] = format(ctx.trace_id, "032x")
            out["span_id"] = format(ctx.span_id, "016x")
        for key in ("request_id", "outcome", "mrz_result"):
            if hasattr(record, key):
                out[key] = getattr(record, key)
        if record.exc_info:
            out["exc_type"] = record.exc_info[0].__name__
        return json.dumps(out)


def _setup_stdout_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())


def setup(app) -> None:
    """Configure providers and auto-instrumentation. Call once at import time."""
    global _enabled
    _setup_stdout_logging()

    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or os.getenv("OTEL_SDK_DISABLED", "").lower() == "true":
        log.info("OTLP endpoint not set; telemetry export disabled")
        return

    # Stable HTTP semantic conventions (http.server.request.duration in seconds,
    # http.request.method, url.path ...) instead of the legacy names.
    os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "http")

    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    # service.name, service.version, deployment.environment etc. come from
    # OTEL_SERVICE_NAME / OTEL_RESOURCE_ATTRIBUTES set by the Helm chart.
    resource = Resource.create({"service.name": SERVICE_NAME})

    tp = TracerProvider(resource=resource)
    tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tp)

    def buckets(name, bounds):
        return View(instrument_name=name, aggregation=ExplicitBucketHistogramAggregation(bounds))

    # Exemplars use the SDK default (trace_based): a measurement taken inside a
    # sampled span carries its trace_id, which Grafana turns into a link.
    mp = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter(), export_interval_millis=10_000)],
        views=[
            buckets("ocr.extract.duration", LATENCY_BUCKETS),
            buckets("ocr.stage.duration", LATENCY_BUCKETS),
            buckets("ocr.upstream.time_to_first_token", LATENCY_BUCKETS),
            buckets("gen_ai.client.operation.duration", LATENCY_BUCKETS),
            buckets("gen_ai.client.token.usage", TOKEN_BUCKETS),
            buckets("ocr.image.size", BYTES_BUCKETS),
            buckets("http.server.request.duration", LATENCY_BUCKETS),
            buckets("http.client.request.duration", LATENCY_BUCKETS),
        ],
    )
    metrics.set_meter_provider(mp)

    lp = LoggerProvider(resource=resource)
    lp.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    set_logger_provider(lp)
    logging.getLogger().addHandler(LoggingHandler(logger_provider=lp))

    # Probes would otherwise produce a span every few seconds per pod, and the
    # per-message ASGI receive/send spans add noise without information.
    FastAPIInstrumentor.instrument_app(app, excluded_urls="healthz,readyz", exclude_spans=["receive", "send"])
    HTTPXClientInstrumentor().instrument()
    _enabled = True
    log.info("telemetry export enabled")


tracer = trace.get_tracer("ocr-api")
meter = metrics.get_meter("ocr-api")

# --- Instruments -------------------------------------------------------------
# Attribute values are all low-cardinality enums (see the cardinality budget in
# observability/README.md). Never add request IDs, file names or user data.

extract_duration = meter.create_histogram(
    "ocr.extract.duration", unit="s",
    description="End-to-end /extract handling time inside the API, by outcome")
extractions = meter.create_counter(
    "ocr.extractions", unit="{extraction}",
    description="Completed /extract requests by outcome")
stage_duration = meter.create_histogram(
    "ocr.stage.duration", unit="s",
    description="Time per API stage: preprocess, inference, parse, mrz")
mrz_checks = meter.create_counter(
    "ocr.mrz.checks", unit="{check}",
    description="MRZ check-digit validation result per extraction (valid, invalid, missing, unparseable)")
field_agreement = meter.create_counter(
    "ocr.mrz.field_agreement", unit="{field}",
    description="Whether the VLM's visual-zone value matched the MRZ value, per field (valid MRZ only)")
image_size = meter.create_histogram(
    "ocr.image.size", unit="By", description="Image bytes sent to the model after resizing")
upstream_ttft = meter.create_histogram(
    "ocr.upstream.time_to_first_token", unit="s",
    description="Client-side time to first streamed token from the model endpoint")
ratelimit_remaining = meter.create_gauge(
    "ocr.upstream.ratelimit.remaining", unit="1",
    description="Last rate-limit remaining value reported by the model provider, by limit type")

# OTel GenAI semantic conventions (client side).
genai_duration = meter.create_histogram(
    "gen_ai.client.operation.duration", unit="s", description="GenAI operation duration")
genai_tokens = meter.create_histogram(
    "gen_ai.client.token.usage", unit="{token}", description="Input and output tokens per operation")
