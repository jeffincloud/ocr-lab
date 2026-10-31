# Observability for the OCR lab

Telemetry for the four layers of an LLM inference app (hardware, network, application, inference),
built from CNCF/OSS parts, collected through OpenTelemetry only, and wired so you can move between
metrics, traces and logs without copying IDs.

```
 k6 / browser ─► Envoy Gateway ─► nginx ─► ocr-api ─► Envoy ─► llm-d EPP ─► vLLM ─► GPU
                  /stats           timed    OTel SDK:           picks a      /metrics   DCGM
                                   logs     traces, metrics     replica      + OTLP     exporter
                                            + exemplars, logs   /metrics,    spans
                                                                OTLP spans
      │ OTLP (push)          │ Prometheus format (pulled by the collector)    │ pod logs, k8s events, kubelet stats
      ▼                      ▼                                                ▼
   ┌──────────────────────────── OpenTelemetry Collector (DaemonSet) ───────────────────────────┐
   │ receivers: otlp · prometheus (vLLM, EPP, Envoy, DCGM, kube-state-metrics) · kubeletstats  │
   │            filelog (pods) · k8sobjects (events)                                            │
   │ PII: fail-closed span attrs, value scrubbing · cardinality guard · tail sampling · k8s attrs│
   └──────┬──────────────────────────┬────────────────────────────────┬────────────────────────┘
          ▼ OTLP                     ▼ OTLP                           ▼ OTLP
        Tempo                    Prometheus                          Loki
   (span metrics,           (OTLP store: exemplars,            (trace_id as
    service graph)           SLO/cost rules; scrapes nothing)   structured metadata)
          └──────────────────────────── Grafana ─────────────────────────┘
```

## OTel-first collection

The collector is the only agent and every signal reaches a backend as OTLP:

- **Pushed over OTLP** by the code that produces it: the API (traces, metrics with exemplars,
  logs), vLLM and the llm-d EPP (traces, via the LLMInferenceService `tracing` block), the mock,
  and the collector's own metrics.
- **Pulled by the collector** and converted to OTLP where a component only speaks Prometheus
  format: vLLM, the EPP, Envoy, DCGM and kube-state-metrics (`charts/observability` `scrape:`
  values → a `prometheus` receiver with node-local pod discovery). Metric names survive the trip
  unchanged (`vllm:time_to_first_token_seconds`), so dashboards work against either path.
- **Read from the node**: `kubeletstats` (pod/container CPU, memory, limit utilization; replaces
  cAdvisor), `filelog` (pod logs, named by `app.kubernetes.io/name`), `k8sobjects` (events, as
  `service_name="k8s-events"`).

Prometheus only stores and evaluates rules: no ServiceMonitors, PodMonitors or node-exporter. The
benefit is one pipeline, so the PII, cardinality and sampling rules apply to every signal no
matter where it came from. The cost: the collector is a single point of failure for telemetry,
so its own metrics (`otelcol_*`) are pushed straight to Prometheus and alerted on.
kube-state-metrics stays because no OTel receiver gives pod creation→Ready timestamps.

| Path | What |
|---|---|
| `local/compose.yaml` | Everything on a laptop with the mock model. No GPU, no Kubernetes. |
| `install.sh`, `values/` | The same stack on the lab cluster (kube-prometheus-stack, Loki, Tempo, Collector, DCGM). |
| `../charts/observability/` | Collector pipeline and scrape targets, SLO/cost/cold-start rules, dashboards. Shared by both. |
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

`scripts/lab-up.sh` installs all of it (PROFILE=local on kind with the mock, PROFILE=gpu on the
GPU node). By hand:

```bash
KUBECONFIG=~/.kube/ocr-lab.config ./observability/install.sh          # GPU=false skips DCGM
helm upgrade --install model charts/model-llmd                           # tracing on by default
```

## Context correlation

| From | To | How |
|---|---|---|
| Latency panel | One slow request's trace | Exemplars. The API records histograms inside the request span, so each sample carries `trace_id`. Prometheus stores exemplars (feature flag), Grafana links `trace_id` to Tempo. |
| Trace | Its logs | Tempo → Loki on `trace_id` (Loki keeps it as structured metadata on OTLP logs). |
| Log line | Its trace | Loki derived field on `trace_id` (OTLP metadata or the JSON stdout line). |
| Trace | Engine/GPU state at that moment | Tempo "traces to metrics": queue p95, KV cache, SM active for the span's time window. |
| API span | EPP and vLLM spans | W3C `traceparent` propagated by the httpx instrumentation; KServe turns on `--otlp-traces-endpoint` for vLLM and tracing for the EPP, whose scheduling spans (filters, scorers, pick) sit between the API call and `llm_request`. |
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
| `ocr_extract_duration_seconds` | outcome × backend | 7 × 2 | 14 × 26 buckets ≈ 365 |
| `ocr_extractions_total` | outcome × backend | 7 × 2 | 14 |
| `ocr_stage_duration_seconds` | stage | 4 | 4 × 26 ≈ 105 |
| `ocr_mrz_checks_total` | result | 4 | 4 |
| `ocr_mrz_field_agreement_total` | field × agree | 6 × 2 | 12 |
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
