"""The OCR lab's full observability stack, in the CNCF deck palette.  python3 stack.py out.svg"""
import sys
from html import escape

BLUE, BLUE2, TURQ, GREEN, ORANGE, STONE = "#0086FF", "#058DC7", "#93EAFF", "#50B432", "#ED561B", "#E5E5E5"
INK, MUTED, LINE, SOFT = "#111827", "#4B5563", "#D0D7DE", "#F6F8FA"
TINT_A, TINT_B, DARK = "#EEF6FF", "#EDFAFE", "#0D1117"
SIG = {"T": GREEN, "M": BLUE, "L": ORANGE}
W, H = 1700, 1150
F = 'font-family="Arial, Helvetica, sans-serif"'
out = []
add = out.append


def text(x, y, s, size=15, fill=INK, weight="normal", anchor="start"):
    add(f'<text x="{x:.1f}" y="{y:.1f}" {F} font-size="{size}" fill="{fill}" font-weight="{weight}" text-anchor="{anchor}">{escape(s)}</text>')


def rect(x, y, w, h, fill, rx=10, stroke="none", sw=1, dash=""):
    d = f'stroke-dasharray="{dash}"' if dash else ""
    add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {d}/>')


def line(x1, y1, x2, y2, col, w=2.5, dash="", head=True):
    d = f'stroke-dasharray="{dash}"' if dash else ""
    add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{col}" stroke-width="{w}" {d}/>')
    if head:
        if x1 == x2:
            s = 1 if y2 > y1 else -1
            add(f'<path d="M{x2 - 6:.1f} {y2 - 10 * s:.1f}L{x2:.1f} {y2:.1f}L{x2 + 6:.1f} {y2 - 10 * s:.1f}z" fill="{col}"/>')
        else:
            s = 1 if x2 > x1 else -1
            add(f'<path d="M{x2 - 10 * s:.1f} {y2 - 6:.1f}L{x2:.1f} {y2:.1f}L{x2 - 10 * s:.1f} {y2 + 6:.1f}z" fill="{col}"/>')


add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
rect(0, 0, W, H, "#FFFFFF", rx=0)
text(30, 50, "How the OCR lab is observed: one OpenTelemetry pipeline, three signals, one request ID", 30, INK, "bold")

# legend
lx = 30
for col, lab in ((GREEN, "traces"), (BLUE, "metrics"), (ORANGE, "logs")):
    add(f'<circle cx="{lx + 6}" cy="76" r="6" fill="{col}"/>'); text(lx + 18, 81, lab, 14, MUTED); lx += 92
line(lx + 6, 76, lx + 44, 76, MUTED, 2.5, head=False); text(lx + 52, 81, "pushed over OTLP", 14, MUTED); lx += 190
line(lx, 76, lx + 38, 76, MUTED, 2.5, "6 5", head=False); text(lx + 46, 81, "scraped or read by the collector", 14, MUTED); lx += 290
line(lx, 76, lx + 38, 76, TURQ, 3, head=False); text(lx + 46, 81, "context that travels with the request", 14, MUTED)

# --- row A: request path ----------------------------------------------------------------
ya, ha = 104, 164
comps = [
    ("Envoy Gateway", "edge, port 80", [("T", "EnvoyProxy: spans as envoy"), ("M", "/stats scraped"), ("L", "JSON log with trace_id")]),
    ("nginx", "frontend, /api proxy", [("L", "JSON log, request_id"), ("T", "no spans; passes"), ("T", "traceparent through")]),
    ("FastAPI API", "MRZ check, GenAI client", [("T", "OTel SDK: ocr.* spans"), ("M", "SDK + exemplars"), ("L", "JSON + OTLP, trace_id")]),
    ("llm-d scheduler", "EPP, picks the pod", [("T", "KServe tracing block"), ("M", "/metrics + bearer token"), ("L", "JSON with x-request-id")]),
    ("vLLM", "Qwen3.5-9B FP8", [("T", "--otlp-traces-endpoint"), ("M", "/metrics scraped"), ("L", "stdout: capacity, start-up")]),
    ("L40S GPU", "DCGM exporter", [("M", "power, temp, clocks, XID"), ("M", "no SM activity here"), ("M", "(profiling crashes it)")]),
]
cw, gap, x0 = 248, 30, 30
text(x0, ya - 6, "", 1)
for i, (name, role, items) in enumerate(comps):
    x = x0 + i * (cw + gap)
    rect(x, ya, cw, ha, TINT_A if i % 2 == 0 else TINT_B, rx=14)
    text(x + 16, ya + 32, name, 19, BLUE if i % 2 == 0 else BLUE2, "bold")
    text(x + 16, ya + 54, role, 13.5, MUTED)
    for j, (k, s) in enumerate(items):
        yy = ya + 90 + j * 30
        add(f'<circle cx="{x + 22}" cy="{yy - 5}" r="5.5" fill="{SIG[k]}"/>')
        text(x + 36, yy, s, 14, INK)
    if i < len(comps) - 1:
        line(x + cw + 2, ya + 44, x + cw + gap - 2, ya + 44, TURQ, 3)
hops = ["traceparent", "X-Request-ID", "via Envoy", "picks pod", "CUDA"]
for i, h in enumerate(hops):
    text(x0 + (i + 1) * (cw + gap) - gap / 2, ya - 8, h, 12, BLUE2, "bold", "middle")
text(x0, ya + ha + 22, "Visitor or k6  →  every hop adds its spans to the same trace; the API sends Envoy's X-Request-ID on to the model, and vLLM names its request chatcmpl-<that id>.", 13.5, MUTED)

# --- emission into the collector --------------------------------------------------------
yc = 334
pushes = {0: ["T"], 2: ["T", "M", "L"], 3: ["T"], 4: ["T"]}
pulls = {0: ["M", "L"], 1: ["L"], 3: ["M", "L"], 4: ["M", "L"], 5: ["M"]}
for i in range(6):
    x = x0 + i * (cw + gap)
    ks = [(k, False) for k in pushes.get(i, [])] + [(k, True) for k in pulls.get(i, [])]
    for j, (k, dashed) in enumerate(ks):
        lx_ = x + 30 + j * 30
        line(lx_, ya + ha + 34, lx_, yc - 2, SIG[k], 2.5, "6 5" if dashed else "")

# --- platform sources -------------------------------------------------------------------
# --- the collector ----------------------------------------------------------------------
cx0, cw_ = 30, W - 60
rect(cx0, yc, cw_, 236, SOFT, rx=16, stroke=LINE)
text(cx0 + 22, yc + 34, "OpenTelemetry Collector", 22, BLUE, "bold")
text(cx0 + 290, yc + 33, "DaemonSet, the only agent. Prometheus scrapes nothing; everything arrives here and leaves as OTLP.", 14, MUTED)
cols = [("Receivers", cx0 + 22, 330), ("Processors, in order", cx0 + 380, 900), ("Exporters", cx0 + 1310, 300)]
for t, x, w in cols:
    text(x, yc + 66, t, 15, INK, "bold")
recv = [("otlp  (gRPC 4317, HTTP 4318)", INK), ("prometheus  (vLLM, EPP, Envoy, DCGM, KSM)", INK),
        ("kubeletstats  (pod CPU, memory)", INK), ("filelog  (pod logs)", INK), ("k8sobjects  (events)", INK), ("webhookevent  (Alertmanager)", INK)]
for j, (s, c) in enumerate(recv):
    text(cx0 + 22, yc + 94 + j * 22, s, 13.5, c)
procs = [("memory_limiter", "back-pressure"), ("k8sattributes", "pod, namespace, node"), ("redaction", "fail-closed span keys"),
         ("transform/scrub", "MRZ, images, tokens"), ("mask_ips", "visitor IP → /24"), ("cardinality", "no IDs on metrics"),
         ("k8s_logs", "name logs like spans"), ("tail_sampling", "errors, >25 s, 70 s wait"), ("batch", "")]
pw_, ph_ = 190, 46
for j, (n, d) in enumerate(procs):
    px = cx0 + 380 + (j % 4) * (pw_ + 14)
    py = yc + 80 + (j // 4) * (ph_ + 10)
    if j == 8:
        px, py = cx0 + 380 + 3 * (pw_ + 14), yc + 80 + 2 * (ph_ + 10)
    rect(px, py, pw_, ph_, "#FFFFFF", rx=8, stroke=LINE)
    text(px + 12, py + 20, n, 14, BLUE2, "bold")
    if d:
        text(px + 12, py + 38, d, 12, MUTED)
for j, (s, c) in enumerate([("otlp → Tempo", GREEN), ("otlphttp → Prometheus OTLP", BLUE), ("otlphttp → Loki OTLP", ORANGE),
                            ("own metrics → Prometheus", MUTED), ("(separate path, alerted on)", MUTED)]):
    text(cx0 + 1310, yc + 94 + j * 24, s, 14, c, "bold" if j < 3 else "normal")

# platform feed note (left, inside collector row bottom)
text(cx0 + 22, yc + 226, "Platform sources: kubelet, kube-state-metrics, Kubernetes events, Alertmanager.", 12.5, MUTED)

# --- backends ---------------------------------------------------------------------------
yb = 624
bw = (W - 60 - 3 * 30) / 4
backs = [
    ("Prometheus", BLUE, ["OTLP store, exemplars on", "SLO, cost, cold-start rules", "583 metric names"]),
    ("Tempo", GREEN, ["traces, 23 spans per request", "metrics generator: service", "graph and span metrics"]),
    ("Loki", ORANGE, ["10 log sources incl. alerts", "trace_id in API and Envoy", "lines; IPs masked"]),
    ("Alertmanager", BLUE2, ["fed by Prometheus rules", "alerts → collector → Loki", "(no pager configured)"]),
]
for i, (n, col, lines_) in enumerate(backs):
    x = 30 + i * (bw + 30)
    rect(x, yb, bw, 122, "#FFFFFF", rx=14, stroke=col, sw=2)
    text(x + 18, yb + 32, n, 20, col, "bold")
    for j, s in enumerate(lines_):
        text(x + 18, yb + 58 + j * 21, s, 13.5, INK)
for i, col in enumerate((GREEN, BLUE, ORANGE)):
    x = [30 + 1 * (bw + 30), 30, 30 + 2 * (bw + 30)][i] + bw / 2
    line(x, yc + 236, x, yb - 2, col, 3)

# --- Grafana ----------------------------------------------------------------------------
yg = 776
rect(30, yg, W - 60, 64, TINT_A, rx=14)
text(52, yg + 40, "Grafana", 22, BLUE, "bold")
text(170, yg + 39, "7 dashboards as code: SLOs and quality · Request journey · Inference · GPU · Routing · Cold start · Cost.  Tunnel only.", 15, INK)

# --- correlation ------------------------------------------------------------------------
yk = 866
text(30, yk + 22, "How the signals join up", 20, INK, "bold")
cards = [
    ("traceparent", "W3C trace context through Envoy, nginx, HTTPX, Envoy, llm-d and vLLM: one trace, four services."),
    ("X-Request-ID", "One ID in Envoy (both hops), nginx, the API, llm-d's logs and vLLM's chatcmpl-<id>."),
    ("Exemplars", "A dot on the latency histogram carries the trace_id of the request it measured."),
    ("trace_id in logs", "Span → its log lines: exact for API and Envoy, by time window for vLLM and llm-d."),
    ("Resource attributes", "service.name and k8s.pod.name are the join keys between metrics, spans and logs."),
    ("Traces → metrics", "From any span, Grafana shows queue p95, KV cache and GPU power for that minute."),
]
kw, kh = (W - 60 - 2 * 20) / 3, 100
for i, (t, d) in enumerate(cards):
    x, y = 30 + (i % 3) * (kw + 20), yk + 40 + (i // 3) * (kh + 14)
    rect(x, y, kw, kh, "#FFFFFF", rx=12, stroke=LINE)
    rect(x, y, 6, kh, TURQ, rx=3)
    text(x + 22, y + 32, t, 17, BLUE2, "bold")
    words, ln, yy = d.split(), "", y + 58
    for w_ in words:
        if len(ln) + len(w_) > 62:
            text(x + 22, yy, ln, 13.5, INK); yy += 20; ln = ""
        ln = (ln + " " + w_).strip()
    text(x + 22, yy, ln, 13.5, INK)
add("</svg>")
open(sys.argv[1], "w").write("\n".join(out))
