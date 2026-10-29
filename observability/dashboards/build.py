#!/usr/bin/env python3
"""Dashboards as code: writes Grafana JSON to charts/observability/files/dashboards/.

The Helm chart ships them as ConfigMaps (Grafana sidecar) and the local compose
stack mounts the same directory, so there's one source of truth.

    python observability/dashboards/build.py

Layout rule: each dashboard reads top-down from the user's view to the
silicon (SLOs -> API -> engine -> GPU), every row shares the time axis, and
k6 runs show up as annotations. Datasource UIDs: prometheus, tempo, loki.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = ROOT / "charts/observability/files/dashboards"
PROM = {"type": "prometheus", "uid": "prometheus"}
TEMPO = {"type": "tempo", "uid": "tempo"}
LOKI = {"type": "loki", "uid": "loki"}

# Status colours are reserved for SLO state; series use Grafana's palette.
GOOD, WARN, BAD = "green", "orange", "red"


class Board:
    def __init__(self, uid, title, description, tags=()):
        self.uid, self.title, self.description = uid, title, description
        self.tags = ["ocr-lab", *tags]
        self.panels, self.y, self.x, self.row_h, self.next_id = [], 0, 0, 0, 1
        self.variables = []

    def _place(self, w, h):
        if self.x + w > 24:
            self.x, self.y = 0, self.y + self.row_h
            self.row_h = 0
        pos = {"x": self.x, "y": self.y, "w": w, "h": h}
        self.x += w
        self.row_h = max(self.row_h, h)
        return pos

    def row(self, title):
        if self.x:
            self.x, self.y, self.row_h = 0, self.y + self.row_h, 0
        self.panels.append({"type": "row", "title": title, "id": self.next_id, "collapsed": False,
                            "gridPos": {"x": 0, "y": self.y, "w": 24, "h": 1}, "panels": []})
        self.next_id += 1
        self.y += 1

    def add(self, panel, w, h):
        panel["id"] = self.next_id
        panel["gridPos"] = self._place(w, h)
        self.next_id += 1
        self.panels.append(panel)

    def var(self, name, query, label=None, include_all=True):
        self.variables.append({
            "name": name, "label": label or name, "type": "query", "datasource": PROM,
            "query": {"query": query, "refId": name}, "refresh": 2, "includeAll": include_all,
            "multi": include_all, "current": {"text": "All", "value": "$__all"} if include_all else {},
        })

    def json(self):
        return {
            "uid": self.uid, "title": self.title, "description": self.description, "tags": self.tags,
            "schemaVersion": 39, "editable": True, "graphTooltip": 1, "refresh": "10s",
            "time": {"from": "now-30m", "to": "now"},
            "templating": {"list": self.variables},
            "annotations": {"list": [{
                "name": "k6 runs", "datasource": PROM, "enable": True, "iconColor": "purple",
                "expr": 'changes(k6_http_reqs_total[1m]) > 0 unless changes(k6_http_reqs_total[1m] offset 1m) > 0',
                "titleFormat": "load test started", "tagKeys": "testid,scenario",
            }]},
            "panels": self.panels,
        }


def target(expr, legend="", ref="A", exemplar=False, instant=False):
    t = {"datasource": PROM, "expr": expr, "legendFormat": legend, "refId": ref}
    if exemplar:
        t["exemplar"] = True
    if instant:
        t.update({"instant": True, "range": False})
    return t


def ts(title, targets, unit="short", desc="", stack=False, min0=True, max_=None, thresholds=None, bars=False):
    custom = {"lineWidth": 2, "fillOpacity": 10 if stack else 0, "showPoints": "never",
              "stacking": {"mode": "normal" if stack else "none"}}
    if bars:
        custom.update({"drawStyle": "bars", "fillOpacity": 80})
    defaults = {"unit": unit, "custom": custom}
    if min0:
        defaults["min"] = 0
    if max_ is not None:
        defaults["max"] = max_
    if thresholds:
        defaults["thresholds"] = {"mode": "absolute", "steps": thresholds}
        custom["thresholdsStyle"] = {"mode": "dashed"}
    return {"type": "timeseries", "title": title, "description": desc, "datasource": PROM,
            "targets": [t if isinstance(t, dict) else target(*t, ref=chr(65 + i)) for i, t in enumerate(targets)],
            "fieldConfig": {"defaults": defaults, "overrides": []},
            "options": {"legend": {"displayMode": "list", "placement": "bottom"},
                        "tooltip": {"mode": "multi", "sort": "desc"}}}


def stat(title, expr, unit="percentunit", desc="", steps=None, decimals=2, legend=""):
    return {"type": "stat", "title": title, "description": desc, "datasource": PROM,
            "targets": [target(expr, legend, instant=True)],
            "fieldConfig": {"defaults": {"unit": unit, "decimals": decimals, "color": {"mode": "thresholds"},
                                         "thresholds": {"mode": "absolute",
                                                        "steps": steps or [{"color": "text", "value": None}]}},
                            "overrides": []},
            "options": {"colorMode": "value", "graphMode": "none", "textMode": "value_and_name",
                        "reduceOptions": {"calcs": ["lastNotNull"]}}}


def text(title, md):
    return {"type": "text", "title": title, "options": {"mode": "markdown", "content": md}}


def heatmap(title, expr, unit="s", desc=""):
    return {"type": "heatmap", "title": title, "description": desc, "datasource": PROM,
            "targets": [{"datasource": PROM, "expr": expr, "format": "heatmap", "legendFormat": "{{le}}",
                         "refId": "A"}],
            "options": {"calculate": False, "yAxis": {"unit": unit},
                        "color": {"mode": "scheme", "scheme": "Blues", "steps": 64},
                        "cellGap": 1, "tooltip": {"show": True, "yHistogram": True}},
            "fieldConfig": {"defaults": {}, "overrides": []}}


def logs(title, expr, desc=""):
    return {"type": "logs", "title": title, "description": desc, "datasource": LOKI,
            "targets": [{"datasource": LOKI, "expr": expr, "refId": "A"}],
            "options": {"showTime": True, "wrapLogMessage": True, "enableLogDetails": True,
                        "sortOrder": "Descending"}}


def slo_steps(objective):
    return [{"color": BAD, "value": None}, {"color": WARN, "value": objective - 0.005},
            {"color": GOOD, "value": objective}]


def q(metric_filter, quantile, by="le"):
    return f"histogram_quantile({quantile}, sum by ({by}) (rate({metric_filter}[$__rate_interval])))"


# --- 1. SLOs ---------------------------------------------------------------------------------
def slo_board():
    b = Board("ocr-slo", "OCR · SLOs & quality",
              "Is the OCR service doing its job? Availability, latency and correctness against their SLOs, "
              "with error budgets and burn rates. Start here.", ["slo"])
    b.row("Service level objectives (28-day window)")
    slos = [("ocr-availability", "Availability", 0.995), ("ocr-latency", "Latency ≤ 8 s", 0.95),
            ("ocr-mrz-validity", "MRZ check digits valid", 0.98),
            ("ocr-visual-agreement", "Visual fields agree with MRZ", 0.97),
            ("inference-ttft", "Engine TTFT ≤ 2.5 s", 0.95)]
    widths = [5, 5, 5, 5, 4]
    for (slo, label, obj), w in zip(slos, widths):
        b.add(stat(label, f'1 - slo:sli_error:ratio_rate28d{{slo="{slo}"}}', steps=slo_steps(obj),
                   desc=f"Share of good events over 28 days. Objective {obj:.1%}."), w, 4)
    for (slo, label, obj), w in zip(slos, widths):
        b.add(stat(f"Budget left · {label}", f'slo:period_error_budget_remaining:ratio{{slo="{slo}"}}',
                   steps=[{"color": BAD, "value": None}, {"color": WARN, "value": 0.25}, {"color": GOOD, "value": 0.5}],
                   desc="Share of the 28-day error budget not yet spent. Negative means the SLO is already missed."), w, 3)
    b.add(ts("Burn rate (5m) by SLO", [("slo:current_burn_rate:ratio", "{{slo}}")], "x",
             desc="1x spends the budget exactly over 28 days. Page at 14.4x (1h) or 6x (6h).",
             thresholds=[{"color": "transparent", "value": None}, {"color": WARN, "value": 6}, {"color": BAD, "value": 14.4}]),
          24, 7)

    b.row("Application: what users get")
    b.add(ts("Requests by outcome", [("sum by (outcome) (rate(ocr_extractions_total[$__rate_interval]))", "{{outcome}}")],
             "reqps", stack=True, desc="ok, bad_request (4xx) and the 5xx outcomes that burn the availability budget."), 12, 8)
    b.add(ts("/extract latency (API) — click a dot for the trace", [
        target(q('ocr_extract_duration_seconds_bucket{outcome="ok"}', 0.5), "p50", "A", exemplar=True),
        target(q('ocr_extract_duration_seconds_bucket{outcome="ok"}', 0.95), "p95", "B"),
        target(q('ocr_extract_duration_seconds_bucket{outcome="ok"}', 0.99), "p99", "C")], "s",
        desc="Dots are exemplars: individual requests with their trace ID. Click one to open the trace in Tempo.",
        thresholds=[{"color": "transparent", "value": None}, {"color": BAD, "value": 8}]), 12, 8)

    b.row("Quality: is the answer right?")
    b.add(ts("MRZ check result", [("sum by (result) (rate(ocr_mrz_checks_total[$__rate_interval]))", "{{result}}")],
             "reqps", stack=True,
             desc="valid = ICAO 9303 check digits pass. invalid/unparseable = the model misread the MRZ. "
                  "No labels needed: the document checks itself."), 8, 8)
    b.add(ts("Visual-zone agreement with MRZ, by field", [(
        'sum by (field) (rate(ocr_mrz_field_agreement_total{agree="true"}[$__rate_interval])) / '
        'sum by (field) (rate(ocr_mrz_field_agreement_total[$__rate_interval]))', "{{field}}")], "percentunit",
        min0=False, desc="How often what the model read from the printed page matches the validated MRZ. "
                         "A drop is a visual-reading regression the MRZ override would hide."), 8, 8)
    b.add(ts("Model output problems", [
        ('sum(rate(ocr_extractions_total{outcome="model_output_error"}[$__rate_interval]))', "invalid JSON"),
        ('sum(rate(ocr_mrz_checks_total{result="missing"}[$__rate_interval]))', "MRZ missing")], "reqps",
        desc="Answers that arrived on time but were unusable — invisible to latency/error dashboards."), 8, 8)
    return b


# --- 2. Request journey --------------------------------------------------------------------------
def journey_board():
    b = Board("ocr-journey", "OCR · Request journey",
              "Where does the time go for one extraction? Edge → API stages → model call → engine phases, "
              "plus the service map and correlated logs.", ["traces"])
    b.row("Service map (from traces)")
    b.add({"type": "nodeGraph", "title": "Service graph", "datasource": TEMPO,
           "targets": [{"datasource": TEMPO, "queryType": "serviceMap", "refId": "A"}]}, 12, 10)
    b.add({"type": "table", "title": "Slowest recent traces (click to open)", "datasource": TEMPO,
           "targets": [{"datasource": TEMPO, "queryType": "traceql", "limit": 20, "refId": "A",
                        "query": '{resource.service.name="ocr-api" && span.http.route="/extract"} | select(span.ocr.outcome) '
                                 '| duration > 3s'}]}, 12, 10)

    b.row("API stages")
    b.add(ts("Mean time per API stage", [(
        "sum by (stage) (rate(ocr_stage_duration_seconds_sum[$__rate_interval])) / "
        "sum by (stage) (rate(ocr_stage_duration_seconds_count[$__rate_interval]))", "{{stage}}")], "s", stack=True,
        desc="preprocess (decode/resize/base64), inference (waiting on the model), parse (JSON), mrz (validation)."), 12, 8)
    b.add(ts("Model call: client view vs engine view", [
        (q("gen_ai_client_operation_duration_seconds_bucket", 0.95), "client: model call p95"),
        (q("ocr_upstream_time_to_first_token_seconds_bucket", 0.95), "client: TTFT p95"),
        (q("vllm:time_to_first_token_seconds_bucket", 0.95), "engine: TTFT p95"),
        (q("vllm:e2e_request_latency_seconds_bucket", 0.95), "engine: e2e p95")], "s",
        desc="Client-side numbers are all a closed API gives you. The gap between client and engine lines is "
             "network + HTTP + gateway."), 12, 8)

    b.add(ts("API CPU vs its limit", [
        ('max by (k8s_pod_name) (k8s_container_cpu_limit_utilization_ratio{k8s_container_name="api"})', "{{k8s_pod_name}}")],
        "percentunit", max_=1, thresholds=[{"color": "transparent", "value": None}, {"color": BAD, "value": 0.9}],
        desc="From the collector's kubeletstats receiver. Image resize and base64 are CPU work: near 100% the API "
             "is throttled and the preprocess stage grows."), 24, 6)

    b.row("Engine phases (self-hosted only)")
    b.add(ts("Mean phase time per request", [("vllm:mean_phase_seconds", "{{phase}}")], "s", stack=True,
             desc="queue (waiting for a batch slot), prefill (image + prompt tokens), decode (JSON output)."), 12, 8)
    b.add(ts("Tokens per request", [
        ("sum(rate(vllm:request_prompt_tokens_sum[$__rate_interval])) / sum(rate(vllm:request_prompt_tokens_count[$__rate_interval]))", "prompt (mostly image)"),
        ("sum(rate(vllm:request_generation_tokens_sum[$__rate_interval])) / sum(rate(vllm:request_generation_tokens_count[$__rate_interval]))", "generated")],
        "short", desc="For OCR the prompt is mostly vision tokens, so prefill dominates; output is a short JSON."), 12, 8)

    b.row("Logs (click a trace_id to jump to the trace)")
    b.add(logs("API logs", '{service_name="ocr-api"} | detected_level=~"warn|error" or outcome!="ok"',
               desc="Warnings, errors and non-ok outcomes. Every line carries trace_id."), 24, 10)
    return b


# --- 3. Inference engine -------------------------------------------------------------------------
def engine_board():
    b = Board("ocr-inference", "Inference engine · vLLM",
              "Inside the model server: latency phases, batching and KV-cache pressure. "
              "None of this is visible when calling a closed API.", ["vllm", "inference"])
    b.row("Latency")
    for title, m in [("Time to first token", "vllm:time_to_first_token_seconds_bucket"),
                     ("Inter-token latency", "vllm:inter_token_latency_seconds_bucket"),
                     ("End-to-end (engine)", "vllm:e2e_request_latency_seconds_bucket")]:
        b.add(ts(title, [(q(m, 0.5), "p50"), (q(m, 0.95), "p95"), (q(m, 0.99), "p99")], "s"), 8, 8)
    b.add(heatmap("Queue time distribution", "sum by (le) (rate(vllm:request_queue_time_seconds_bucket[$__rate_interval]))",
                  desc="When this climbs, requests wait for a batch slot: the engine is saturated."), 12, 8)
    b.add(heatmap("Prompt tokens per request", "sum by (le) (rate(vllm:request_prompt_tokens_bucket[$__rate_interval]))",
                  unit="short", desc="Image resolution drives this (one token per 32×32 px for Qwen3.5 and Qwen3-VL)."), 12, 8)

    b.row("Scheduler and KV cache (USE)")
    b.add(ts("Running vs waiting requests", [("sum(vllm:num_requests_running)", "running"),
                                             ("sum(vllm:num_requests_waiting)", "waiting")], "short"), 8, 8)
    b.add(ts("KV cache usage", [("max(vllm:kv_cache_usage_perc)", "KV cache")], "percentunit", max_=1,
             thresholds=[{"color": "transparent", "value": None}, {"color": BAD, "value": 0.9}]), 8, 8)
    b.add(ts("Preemptions and prefix-cache hit ratio", [
        ("sum(rate(vllm:num_preemptions_total[$__rate_interval]))", "preemptions/s"),
        ("vllm:prefix_cache_hit_ratio", "prefix cache hit ratio")], "short",
        desc="Preemptions mean KV pressure. Prefix hits rise when the static prompt comes before the image."), 8, 8)

    b.row("Throughput")
    b.add(ts("Tokens per second", [("sum(rate(vllm:prompt_tokens_total[$__rate_interval]))", "prefill tok/s"),
                                   ("sum(rate(vllm:generation_tokens_total[$__rate_interval]))", "decode tok/s")],
             "short"), 12, 8)
    b.add(ts("Finished requests by reason", [
        ("sum by (finished_reason) (rate(vllm:request_success_total[$__rate_interval]))", "{{finished_reason}}")],
        "reqps", stack=True, desc="length = hit max_tokens (truncated JSON risk)."), 12, 8)
    return b


# --- 3b. Routing: Gateway + llm-d endpoint picker -----------------------------------------------
def routing_board():
    b = Board("ocr-routing", "Routing · Gateway + llm-d",
              "How requests reach a model replica: the Envoy Gateway (network layer), the llm-d endpoint "
              "picker (EPP) that chooses the pod from engine state, and whether the replicas end up balanced. "
              "A closed API hides all of this behind one endpoint.", ["llm-d", "gateway"])
    b.row("Gateway (Envoy)")
    b.add(ts("Requests by response class", [
        ("sum by (envoy_response_code_class) (rate(envoy_http_downstream_rq_xx[$__rate_interval]))", "{{envoy_response_code_class}}xx")],
        "reqps", stack=True, desc="As the edge sees them, before the API. 5xx here and not in the API means the gateway or EPP failed."), 12, 8)
    b.add(ts("Gateway latency", [
        ("histogram_quantile(0.95, sum by (le) (rate(envoy_http_downstream_rq_time_bucket[$__rate_interval]))) / 1000", "p95"),
        ("histogram_quantile(0.50, sum by (le) (rate(envoy_http_downstream_rq_time_bucket[$__rate_interval]))) / 1000", "p50")],
        "s", desc="Downstream request time at Envoy, which includes the EPP call and the model."), 12, 8)

    b.row("Endpoint picker (EPP)")
    b.add(ts("Picks per replica", [
        ('sum by (endpoint_name) (rate(llm_d_epp_scheduler_attempts_total{status="success"}[$__rate_interval]))', "{{endpoint_name}}")],
        "reqps", stack=True, desc="Which vLLM pod the scheduler chose. Round-robin would split evenly; the EPP follows queue, KV and prefix-cache state."), 8, 8)
    b.add(ts("Scheduling latency", [
        (q("llm_d_epp_scheduler_e2e_duration_seconds_bucket", 0.95), "p95"),
        (q("llm_d_epp_scheduler_e2e_duration_seconds_bucket", 0.50), "p50")],
        "s", desc="Time the EPP spends choosing a pod. It sits on every request's critical path."), 8, 8)
    b.add(ts("Time per scheduler plugin (p95)", [
        ("histogram_quantile(0.95, sum by (le, plugin_type) (rate(llm_d_epp_plugin_duration_seconds_bucket[$__rate_interval])))", "{{plugin_type}}")],
        "s", desc="Filters and scorers (queue, KV cache, prefix cache). Traces show the same per request."), 8, 8)
    b.add(ts("Pool state as the EPP sees it", [
        ("max(llm_d_epp_average_queue_size)", "avg queue size"),
        ("max(llm_d_epp_average_kv_cache_utilization)", "avg KV cache"),
        ("max(llm_d_epp_ready_endpoints)", "ready endpoints")], "short",
        desc="The EPP polls each replica's /metrics; these are its averages across the InferencePool."), 12, 8)
    b.add(ts("TTFT seen by the EPP vs by vLLM", [
        (q("llm_d_epp_request_ttft_seconds_bucket", 0.95), "EPP: TTFT p95"),
        (q("vllm:time_to_first_token_seconds_bucket", 0.95), "vLLM: TTFT p95")],
        "s", desc="The router measures first-token time from its side of the pod; the gap to vLLM's own number is "
                  "proxying and transport inside the cluster."), 12, 8)

    b.row("Are the replicas balanced?")
    b.add(ts("Waiting requests per replica", [("sum by (pod) (vllm:num_requests_waiting)", "{{pod}}")], "short",
             desc="A good picker keeps these close. One replica queueing while another idles means routing is off."), 8, 8)
    b.add(ts("KV cache per replica", [("max by (pod) (vllm:kv_cache_usage_perc)", "{{pod}}")], "percentunit", max_=1), 8, 8)
    b.add(ts("Image (multimodal) cache hit ratio", [
        ("sum by (pod) (rate(vllm:mm_cache_hits_total[$__rate_interval])) / clamp_min(sum by (pod) (rate(vllm:mm_cache_queries_total[$__rate_interval])), 1e-9)", "{{pod}}")],
        "percentunit", max_=1, desc="Re-sent images skip the vision encoder when they land on the pod that saw them."), 8, 8)

    b.row("Scheduling traces")
    b.add({"type": "table", "title": "Recent EPP scheduling spans (click to open the trace)", "datasource": TEMPO,
           "targets": [{"datasource": TEMPO, "queryType": "traceql", "limit": 20, "refId": "A",
                        "query": '{resource.service.name="inference-scheduler"}'}]}, 24, 8)
    return b


# --- 4. GPU ----------------------------------------------------------------------------------------
def gpu_board():
    b = Board("ocr-gpu", "GPU · DCGM",
              "The hardware layer. Utilization alone lies; SM/tensor activity, memory bandwidth, power and "
              "clocks tell you what the GPU is really doing.", ["gpu", "dcgm"])
    b.row("Is the GPU busy, and with what?")
    b.add(ts("Utilization vs real activity", [
        ("avg(DCGM_FI_DEV_GPU_UTIL) / 100", "GPU util (any kernel running)"),
        ("avg(DCGM_FI_PROF_SM_ACTIVE)", "SM active"),
        ("avg(DCGM_FI_PROF_PIPE_TENSOR_ACTIVE)", "tensor cores active"),
        ("avg(DCGM_FI_PROF_DRAM_ACTIVE)", "memory bandwidth active")], "percentunit", max_=1,
        desc="Prefill is compute-bound (tensor active), decode is memory-bound (DRAM active). PROF_* fields "
             "may be missing on consumer GPUs."), 12, 9)
    b.add(ts("Framebuffer memory", [("sum(DCGM_FI_DEV_FB_USED) * 1024 * 1024", "used"),
                                    ("sum(DCGM_FI_DEV_FB_FREE) * 1024 * 1024", "free")], "bytes", stack=True,
             desc="vLLM pre-allocates ~90% at start-up for weights + KV cache. High 'used' at idle is not pressure; "
                  "watch the KV cache panel on the engine dashboard instead."), 12, 9)
    b.row("Power, heat and throttling (soak tests)")
    b.add(ts("Power", [("sum(DCGM_FI_DEV_POWER_USAGE)", "W")], "watt"), 8, 8)
    b.add(ts("Temperature", [("max(DCGM_FI_DEV_GPU_TEMP)", "GPU °C")], "celsius",
             thresholds=[{"color": "transparent", "value": None}, {"color": BAD, "value": 83}]), 8, 8)
    b.add(ts("SM clock", [("avg(DCGM_FI_DEV_SM_CLOCK)", "MHz")], "short",
             desc="A falling clock under sustained load = thermal or power throttling."), 8, 8)
    b.row("Efficiency and errors")
    b.add(ts("Generated tokens per joule", [("vllm:tokens_per_joule", "tok/J")], "short"), 12, 8)
    b.add(ts("XID errors and PCIe replays", [("max(DCGM_FI_DEV_XID_ERRORS)", "last XID"),
                                             ("sum(rate(DCGM_FI_DEV_PCIE_REPLAY_COUNTER[$__rate_interval]))", "PCIe replays/s")],
             "short", desc="XID = driver-reported GPU fault (the CUDA 804 story's cousin)."), 12, 8)
    return b


# --- 5. Cold start -----------------------------------------------------------------------------
def coldstart_board():
    b = Board("ocr-coldstart", "OCR · Cold start",
              "From 'pod created' to 'serving': scheduling, image pull, weight load, CUDA graph capture. "
              "Dominates recovery time and is invisible from a closed API.", ["coldstart"])
    b.row("Time to ready")
    b.add(stat("Last model pod time to Ready", "max(ocr:model_pod_time_to_ready_seconds)", unit="s", decimals=0,
               steps=[{"color": GOOD, "value": None}, {"color": WARN, "value": 120}, {"color": BAD, "value": 300}]), 6, 6)
    b.add(ts("Time to Ready per model pod", [("ocr:model_pod_time_to_ready_seconds", "{{pod}}")], "s", bars=True), 18, 6)
    b.row("What happened during start-up")
    b.add(logs("Kubernetes events for model pods",
               '{service_name="k8s-events"} |= "Pulling" or "Pulled" or "Scheduled" or "Started" or "Unhealthy" or "BackOff"',
               desc="Collected by the OTel Collector's k8sobjects receiver: Scheduled → Pulling → Pulled → Started → probes."), 12, 12)
    b.add(logs("vLLM start-up milestones",
               '{k8s_namespace_name=~".+"} |~ "(?i)(loading weights took|model loading took|graph capturing finished|'
               'starting vllm api server|application startup complete|init engine)"',
               desc="vLLM logs its own phase timings: weight load, profiling/KV allocation, CUDA graph capture."), 12, 12)
    b.row("Impact on users")
    b.add(ts("Errors and latency while the model was unavailable", [
        ('sum(rate(ocr_extractions_total{outcome=~"upstream_.*"}[$__rate_interval]))', "upstream errors/s"),
        ("sum(up{job=~\".*vllm.*\"})", "model targets up")], "short"), 24, 7)
    return b


# --- 6. Cost and the closed-API comparison ---------------------------------------------------------
def cost_board():
    b = Board("ocr-cost", "OCR · Cost & visibility: self-hosted vs closed API",
              "Cost per request for each backend, and what each one lets you see. Set prices in "
              "charts/observability/values.yaml (pricing).", ["cost"])
    b.var("provider", "label_values(gen_ai_client_operation_duration_seconds_count, gen_ai_provider_name)", "Provider")
    b.row("Cost per 1,000 extractions")
    b.add(ts("Cost per 1k extractions", [("ocr:cost_per_1k_extractions_usd", "{{pricing}}")], "currencyUSD",
             desc="Self-hosted: GPU $/h ÷ extractions/h, so it falls as utilization rises. Hosted API: tokens × price, "
                  "flat per request."), 12, 8)
    b.add(stat("Self-hosted floor (best throughput in last 24h)", "ocr:cost_per_1k_extractions_at_peak_usd",
               unit="currencyUSD", decimals=3), 6, 8)
    b.add(stat("GPU tokens per dollar", "ocr:gpu_tokens_per_usd", unit="short", decimals=0), 6, 8)
    b.row("What each backend lets you observe")
    b.add(ts("Both: client latency of the model call ($provider)", [
        (q('gen_ai_client_operation_duration_seconds_bucket{gen_ai_provider_name=~"$provider"}', 0.95, "le, gen_ai_provider_name"),
         "p95 {{gen_ai_provider_name}}")], "s"), 8, 8)
    b.add(ts("Both: tokens per request ($provider)", [(
        'sum by (gen_ai_provider_name, gen_ai_token_type) (rate(gen_ai_client_token_usage_sum{gen_ai_provider_name=~"$provider"}[$__rate_interval])) / '
        'sum by (gen_ai_provider_name, gen_ai_token_type) (rate(gen_ai_client_token_usage_count{gen_ai_provider_name=~"$provider"}[$__rate_interval]))',
        "{{gen_ai_provider_name}} {{gen_ai_token_type}}")], "short"), 8, 8)
    b.add(ts("Closed API only: rate-limit headroom", [
        ("min by (limit) (ocr_upstream_ratelimit_remaining)", "{{limit}} remaining")], "short",
        desc="From x-ratelimit-* / anthropic-ratelimit-* response headers: the provider's capacity, not yours."), 8, 8)
    b.add(text("Self-hosted only", (
        "Queue time, prefill vs decode, batch size, KV-cache usage, preemptions, prefix-cache hits, "
        "GPU SM/tensor/memory activity, power, clocks, XID errors, cold-start phases, exact model weights.\n\n"
        "A closed API returns **latency, token usage, a request ID and rate-limit headers**. Everything else "
        "on the *Inference engine* and *GPU* dashboards has no equivalent.")), 24, 4)
    return b


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for build in (slo_board, journey_board, engine_board, routing_board, gpu_board, coldstart_board, cost_board):
        b = build()
        (OUT / f"{b.uid}.json").write_text(json.dumps(b.json(), indent=2) + "\n")
        print(f"wrote {b.uid}.json ({len(b.panels)} panels)")


if __name__ == "__main__":
    main()
