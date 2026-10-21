#!/usr/bin/env python3
"""Send deliberately leaky telemetry through the collector and print where to look.

Emits one span and one log record that contain fake passport data the way a
careless developer might: a custom attribute with the surname, an exception
whose message carries an MRZ line, a base64 image in a log line. The
collector's PII layer should drop or mask all of it. Open the printed trace
ID in Grafana (Explore -> Tempo) and check what actually got stored.

    OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 python tools/pii-probe/probe.py
"""
import logging

from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import SimpleLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

FAKE_MRZ_1 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<"
FAKE_MRZ_2 = "L898902C36UTO7408122F1204159ZE184226B<<<<<10"

resource = Resource.create({"service.name": "pii-probe"})
tp = TracerProvider(resource=resource)
tp.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter()))
lp = LoggerProvider(resource=resource)
lp.add_log_record_processor(SimpleLogRecordProcessor(OTLPLogExporter()))
set_logger_provider(lp)
log = logging.getLogger("pii-probe")
log.addHandler(LoggingHandler(logger_provider=lp))
log.setLevel(logging.INFO)

tracer = tp.get_tracer("pii-probe")
with tracer.start_as_current_span("leaky-operation") as span:
    span.set_attribute("passport.surname", "ERIKSSON")           # not allowlisted -> dropped
    span.set_attribute("gen_ai.input.messages", "[image] read this passport")  # content -> dropped
    span.set_attribute("gen_ai.usage.input_tokens", 812)        # allowlisted -> kept
    span.record_exception(ValueError(f"bad MRZ {FAKE_MRZ_1} {FAKE_MRZ_2}"))  # masked in the event
    log.info("model said %s and image was data:image/png;base64,iVBORw0KGgoAAAANSUhEUg==", FAKE_MRZ_2)
    trace_id = format(span.get_span_context().trace_id, "032x")

tp.shutdown()
lp.shutdown()
print(f"trace_id={trace_id}")
print("Expect: no passport.surname or gen_ai.input.messages on the span, [MRZ-REDACTED] in the")
print("exception event and in the log line, [IMAGE-REDACTED] instead of the base64 payload.")
