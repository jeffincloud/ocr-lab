# Observability for the OCR lab

Telemetry for the four layers of an LLM inference app (hardware, network, application, inference),
built from CNCF/OSS parts and wired so you can move between metrics, traces and logs without copying IDs.

```
 k6 / browser ──► nginx ──► ocr-api ─────────────► model server ──► GPU
  traceparent     X-Request-ID  OTel SDK: traces,    vLLM (or llm-d EPP + vLLM,   DCGM exporter
                  timed logs    metrics+exemplars,   or apps/mock-llm)
                                logs w/ trace_id     /metrics + OTLP spans
                         │                                 │                       │
                         ▼ OTLP                            ▼                       ▼
                  ┌───────────────────────── OTel Collector ───────┐      Prometheus scrape
                  │ PII: fail-closed span attrs, value scrubbing   │
                  │ cardinality guard · tail sampling · k8s attrs  │
                  └──────┬───────────────┬──────────────┬──────────┘
                         ▼               ▼              ▼
                     Tempo           Prometheus        Loki
              (span metrics,     (OTLP + exemplars,  (OTLP, trace_id as
               service graph)     SLO/cost rules)     structured metadata)
                         └──────────── Grafana ─────────┘
```

| Path | What |
|---|---|
| `local/compose.yaml` | Everything on a laptop with the mock model. No GPU, no Kubernetes. |
| `install.sh`, `values/` | The same stack on the lab cluster (kube-prometheus-stack, Loki, Tempo, Collector, DCGM). |
| `../charts/observability/` | Collector pipeline, PodMonitors, SLO/cost/cold-start rules, dashboards. Shared by both. |
| `slo/slos.yaml` → `slo/generate.py` | SLOs as code → Prometheus recording rules and burn-rate alerts. |
| `dashboards/build.py` | Dashboards as code → Grafana JSON. |
| `../tools/pii-probe/probe.py` | Sends deliberately leaky telemetry to prove the PII policy works. |

## Run it locally (no GPU)

```bash
python tools/passport-gen/generate.py --count 300 --out loadtest/data/passports
docker compose -f observability/local/compose.yaml up -d --build
k6 run -e BASE_URL=http://localhost:8080/api -e SCENARIO=users -e PEAK_USERS=40 loadtest/k6/ocr-users.js
open http://localhost:3000        # Grafana, folder "OCR Lab"
```

The mock model's latencies are illustrative. Use the local stack to build dashboards, rehearse
recordings and test rules; take every number for the talk from the GPU instance.

## Run it on the cluster

```bash
KUBECONFIG=~/.kube/ocr-lab.config ./observability/install.sh          # GPU=false before the GPU exists
helm upgrade --install ocr-api charts/api --set image.repository=...   # API already points at the collector
helm upgrade --install model charts/model --set tracing.enabled=true --set runtime.image=<vllm-otel image>
```

## Context correlation

| From | To | How |
|---|---|---|
| Latency panel | One slow request's trace | Exemplars. The API records histograms inside the request span, so each sample carries `trace_id`. Prometheus stores exemplars (feature flag), Grafana links `trace_id` to Tempo. |
| Trace | Its logs | Tempo → Loki on `trace_id` (Loki keeps it as structured metadata on OTLP logs). |
| Log line | Its trace | Loki derived field on `trace_id` (OTLP metadata or the JSON stdout line). |
| Trace | Engine/GPU state at that moment | Tempo "traces to metrics": queue p95, KV cache, SM active for the span's time window. |
| API span | vLLM span | W3C `traceparent` propagated by the httpx instrumentation; vLLM continues the trace when started with `--otlp-traces-endpoint`. Under llm-d, the EPP's scheduling spans sit in between. |
| Edge | API | nginx forwards `traceparent` and sets `X-Request-ID`, logged by both. |

Tail sampling and exemplars interact: an exemplar whose trace was dropped is a dead link. The lab
keeps 100% of traces (`TRACE_SAMPLE_PERCENT`), and the latency/error policies keep the traces
exemplars most often point to.

## PII: what may enter telemetry

Passport images and extracted fields are personal data. The rule is **telemetry describes the
request, never its content**, and it's enforced twice:

1. **At the source** (`apps/api`): no image bytes, prompts, model output or field values on spans,
   metrics or logs. GenAI content capture stays off. Exceptions that could echo model output are
   raised `from None` so the chained message (pydantic echoes input values) never reaches a stack trace.
2. **In the collector**, independent of what any developer remembers:
   - `redaction/spans` is **fail-closed**: only attribute keys matching an allowlist of patterns pass.
     A new `passport.surname` attribute is dropped, not stored. `exception.message` passes but is
     value-scanned (MRZ lines, base64 images, bearer tokens are masked). Stack traces are dropped.
   - `transform/scrub` masks the same patterns in log bodies and attributes.
   - The processor adds `redaction.*.count` attributes so you can see that something was removed.

Verify with `tools/pii-probe/probe.py`: it sends a span with a surname, an exception containing an
MRZ, and a log with a base64 image. Only token counts survive; the rest is dropped or masked.

## Cardinality budget

Every distinct combination of label values on a metric is a separate time series that Prometheus
keeps in memory. A label whose values grow with traffic (request ID, user, file name, full URL)
creates a new series per request: memory and query cost grow without bound and dashboards slow down.
A *cardinality budget* is a written limit on that.

For this lab: **every metric label must come from a small, fixed set of values**, and the total for
app metrics should stay under ~5,000 series.

| Metric | Labels | Max values | Series (approx.) |
|---|---|---|---|
| `ocr_extract_duration_seconds` | outcome × backend | 7 × 2 | 14 × 21 buckets ≈ 300 |
| `ocr_extractions_total` | outcome × backend | 7 × 2 | 14 |
| `ocr_stage_duration_seconds` | stage | 4 | 4 × 21 ≈ 85 |
| `ocr_mrz_checks_total` | result | 4 | 4 |
| `ocr_mrz_field_agreement_total` | field × agree | 7 × 2 | 14 |
| `gen_ai_client_*` | model × provider × token type × error type | ~2 × 2 × 2 × 5 | < 1,000 |
| `vllm:*` (scraped) | model_name × pod | 1 × replicas | a few hundred per replica |

Rules: IDs go on spans and exemplars, never on metric labels; no unbounded strings (URLs, error
messages) as labels; adding a label means updating this table. The collector's
`transform/cardinality` deletes known offenders (`url.full`, `client.address`, `ocr.request_id`, ...)
so a mistake can't explode the series count. Check it with
`count by (__name__) ({__name__=~"ocr_.*|gen_ai_.*"})` and `prometheus_tsdb_head_series`.

## SLIs and SLOs

Defined in `slo/slos.yaml` (28-day window), one per layer that matters to the user:

| SLO | Layer | SLI | Objective |
|---|---|---|---|
| ocr-availability | application | non-5xx `/extract` ÷ all except 4xx | 99.5% |
| ocr-latency | application | ok requests ≤ 8 s (API histogram) | 95% |
| ocr-mrz-validity | quality | MRZ passes ICAO check digits | 98% |
| ocr-visual-agreement | quality | printed-page fields agree with the validated MRZ | 97% |
| inference-ttft | inference | engine TTFT ≤ 2.5 s (vLLM histogram) | 95% |

Plus saturation alerts that fire before the SLOs burn: queue p95 > 1 s, KV cache > 90%, preemptions,
GPU thermal throttling, XID errors. Targets are starting points; reset them from the baseline run.

The two quality SLOs are the point to make on stage: latency and errors were green during the
best-known LLM quality incidents. The MRZ gives this app a free, label-free correctness check;
most LLM apps have to build one (golden sets, LLM-as-judge, user feedback).

## Cost per request

`ocr:cost_per_1k_extractions_usd{pricing="self_hosted"|"hosted_api"}`. Self-hosted divides the GPU's
hourly price by successful extractions per hour, so it falls as utilization rises; hosted API
multiplies token usage by list price, so it is flat. Prices live in `charts/observability/values.yaml`.

## Cold start

`ocr:model_pod_time_to_ready_seconds` (kube-state-metrics) gives the total; the phases come from
Kubernetes events (scheduled, image pulled, started) and vLLM's own log lines (weight load, KV cache
allocation, CUDA graph capture), both collected into Loki by the collector. The *Cold start*
dashboard puts them side by side. Kill the model pod during a load test to record it.
