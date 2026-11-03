"""Observability layers infographic for the OCR lab, in the CNCF deck palette.

python3 layers.py data.json out.svg
"""
import json
import sys
from html import escape

BLUE, BLUE2, BLACK, STONE, TURQ, GREEN, ORANGE = "#0086FF", "#058DC7", "#000000", "#E5E5E5", "#93EAFF", "#50B432", "#ED561B"
INK, MUTED, LINE = "#111827", "#4B5563", "#D0D7DE"
TINT_A, TINT_B = "#EEF6FF", "#EDFAFE"
DARK, DARK_GRID, DARK_TEXT = "#0D1117", "#232B36", "#C9D1D9"
SIG = {"M": BLUE, "T": GREEN, "L": ORANGE, "!": ORANGE}
W, H = 1700, 1010
F = 'font-family="Arial, Helvetica, sans-serif"'

out = []
add = out.append


def text(x, y, s, size=16, fill=INK, weight="normal", anchor="start", extra=""):
    add(f'<text x="{x}" y="{y}" {F} font-size="{size}" fill="{fill}" font-weight="{weight}" text-anchor="{anchor}" {extra}>{escape(s)}</text>')


def rect(x, y, w, h, fill, rx=10, stroke="none", sw=1, extra=""):
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}/>')


def arrow(x1, y, x2, color=MUTED):
    add(f'<path d="M{x1} {y}H{x2 - 9}" stroke="{color}" stroke-width="3" fill="none"/>'
        f'<path d="M{x2 - 12} {y - 7}L{x2} {y}L{x2 - 12} {y + 7}z" fill="{color}"/>')


# --- icons, drawn in a 44 x 44 box ---------------------------------------------------
def icon(kind, x, y, c):
    g = f'<g transform="translate({x},{y})">'
    if kind == "user":
        g += f'<circle cx="22" cy="13" r="9" fill="{c}"/><path d="M4 42c0-11 8-17 18-17s18 6 18 17z" fill="{c}"/>'
    elif kind == "route":
        g += (f'<circle cx="8" cy="22" r="6" fill="{c}"/><circle cx="36" cy="8" r="6" fill="{c}"/>'
              f'<circle cx="36" cy="36" r="6" fill="{c}" opacity=".35"/>'
              f'<path d="M14 22H22L30 10M22 22L30 34" stroke="{c}" stroke-width="3.5" fill="none"/>')
    elif kind == "server":
        for i in range(3):
            g += f'<rect x="3" y="{3 + i * 13.5}" width="38" height="10.5" rx="3" fill="{c}"/><circle cx="34" cy="{8.25 + i * 13.5}" r="2" fill="#fff"/>'
    elif kind == "chip":
        g += f'<rect x="9" y="9" width="26" height="26" rx="4" fill="none" stroke="{c}" stroke-width="4"/><rect x="16" y="16" width="12" height="12" rx="2" fill="{c}"/>'
        for i in range(3):
            p = 14 + i * 8
            g += (f'<path d="M{p} 2V9M{p} 35V42M2 {p}H9M35 {p}H42" stroke="{c}" stroke-width="3"/>')
    elif kind == "k8s":
        import math
        pts = " ".join(f"{22 + 20 * math.sin(2 * math.pi * k / 7):.1f},{23 - 20 * math.cos(2 * math.pi * k / 7):.1f}" for k in range(7))
        g += f'<polygon points="{pts}" fill="{c}"/><circle cx="22" cy="23" r="9" fill="none" stroke="#fff" stroke-width="2.5"/>'
        for k in range(7):
            a = 2 * math.pi * k / 7
            g += f'<path d="M22 23L{22 + 14 * math.sin(a):.1f} {23 - 14 * math.cos(a):.1f}" stroke="#fff" stroke-width="2.5"/>'
        g += '<circle cx="22" cy="23" r="3" fill="#fff"/>'
    add(g + "</g>")


# --- the five layers ----------------------------------------------------------------
LAYERS = [
    dict(n=1, title="Application", sub=["User experience and", "request outcome"], icon="user", tint=TINT_A, color=BLUE,
         parts=["Envoy Gateway", "nginx", "FastAPI API"],
         items=[("M", "Extractions per minute by outcome"), ("M", "End-to-end latency (95% < 25 s)"),
                ("M", "First content at the client"), ("M", "Tokens per request (in / out)"),
                ("M", "MRZ check digits valid (quality)"), ("T", "Edge-to-engine trace, one request ID")]),
    dict(n=2, title="Routing", sub=["Which replica serves", "each request (llm-d)"], icon="route", tint=TINT_B, color=BLUE2,
         parts=["Envoy ext_proc", "llm-d EPP", "InferencePool"],
         items=[("M", "Scheduling latency"), ("M", "Picks per replica"), ("M", "Queue and KV cache per replica"),
                ("M", "Prefix-cache hit ratio"), ("T", "Filter, scorer and pick spans"), ("L", "Request ID on every line")]),
    dict(n=3, title="Inference Server", sub=["Model serving runtime", "(vLLM, Qwen3.5-9B FP8)"], icon="server", tint=TINT_A, color=BLUE,
         parts=None,
         items=[("M", "Running vs waiting requests"), ("M", "Queue, prefill and decode time"),
                ("M", "Engine TTFT, inter-token latency"), ("M", "Generated tokens per second"),
                ("M", "KV cache usage, preemptions"), ("M", "Finish reason (length = runaway)")]),
    dict(n=4, title="GPU / Hardware", sub=["One NVIDIA L40S,", "read by DCGM"], icon="chip", tint=TINT_B, color=BLUE2,
         parts=None,
         items=[("M", "Power: 105 W idle, 293 W loaded"), ("M", "Temperature, clock throttling"),
                ("M", "Framebuffer memory used"), ("M", "XID driver errors"), ("M", "Generated tokens per joule"),
                ("!", "GPU utilization: 100% at any load")]),
    dict(n=5, title="Kubernetes", sub=["Platform health (K3s,", "KServe, LLMInferenceService)"], icon="k8s", tint=TINT_A, color=BLUE,
         parts=["Pods", "Node", "Events"],
         items=[("M", "Model pod time to Ready"), ("M", "Pod restarts, availability"), ("M", "CPU and memory vs limits"),
                ("M", "Replicas available"), ("L", "Scheduled, Pulled, Unhealthy events"), ("L", "vLLM start-up: weights, CUDA graphs")]),
]


def illustration(L, x, y, w, h):
    rect(x, y, w, h, "#FFFFFF", rx=10)
    cx = x + w / 2
    if L["n"] == 3:  # requests as queue / prefill / decode segments
        segs = [(ORANGE, .06), (TURQ, .07), (BLUE, .62), (GREEN, .25)]
        for i in range(3):
            yy = y + 18 + i * 30
            text(x + 18, yy + 13, f"Request {i + 1}", 13, MUTED)
            bx, bw = x + 100, w - 120
            off = bx + i * 14
            for col, frac in segs:
                sw = (bw - 28) * frac
                rect(off, yy, sw, 16, col, rx=2)
                off += sw
        text(x + 18, y + h - 12, "queue", 11.5, ORANGE, "bold")
        text(x + 70, y + h - 12, "prefill", 11.5, BLUE2, "bold")
        text(x + 125, y + h - 12, "decode: reasoning", 11.5, BLUE, "bold")
        text(x + 240, y + h - 12, "answer", 11.5, GREEN, "bold")
    elif L["n"] == 4:  # a GPU card
        gx, gy, gw, gh = x + 30, y + 22, w - 60, h - 50
        rect(gx, gy, gw, gh, "#1F2937", rx=8)
        rect(gx + 10, gy + gh, 70, 8, "#B7950B", rx=1)
        for i, fx in enumerate((gx + gw * .58, gx + gw * .82)):
            add(f'<circle cx="{fx}" cy="{gy + gh / 2}" r="{gh * .36}" fill="#111827" stroke="#4B5563" stroke-width="2"/>'
                f'<circle cx="{fx}" cy="{gy + gh / 2}" r="{gh * .1}" fill="#4B5563"/>')
        text(gx + 18, gy + gh / 2 - 4, "L40S", 20, "#FFFFFF", "bold")
        text(gx + 18, gy + gh / 2 + 18, "46 GB", 13, "#9CA3AF")
    elif L["n"] == 1:  # passport to JSON
        rect(x + 18, y + 18, 108, 72, "#F6F8FA", rx=6, stroke=LINE)
        rect(x + 28, y + 28, 26, 32, STONE, rx=3)
        for i in range(3):
            rect(x + 62, y + 30 + i * 10, 52 - i * 10, 5, STONE, rx=2)
        add(f'<text x="{x + 26}" y="{y + 78}" font-family="Consolas, Menlo, monospace" font-size="8.5" fill="{MUTED}">P&lt;UTO&lt;&lt;ERIKSSON&lt;&lt;</text>')
        arrow(x + 134, y + 54, x + 166, BLUE)
        rect(x + 172, y + 18, w - 190, 72, DARK, rx=6)
        for i, (k, v) in enumerate([("mrz", "valid"), ("in", "518"), ("out", "649")]):
            add(f'<text x="{x + 182}" y="{y + 40 + i * 18}" font-family="Consolas, Menlo, monospace" font-size="10.5">'
                f'<tspan fill="{TURQ}">"{k}"</tspan><tspan fill="{DARK_TEXT}">: </tspan><tspan fill="{GREEN if v == "valid" else "#E6EDF3"}">{escape(v)}</tspan></text>')
        text(x + 18, y + h - 12, "passport photo  →  JSON + MRZ verdict", 12, MUTED)
    elif L["n"] == 2:  # request -> EPP -> replica
        rect(x + 12, y + 38, 58, 34, "#F6F8FA", rx=6, stroke=LINE)
        text(x + 41, y + 60, "request", 11.5, MUTED, anchor="middle")
        arrow(x + 72, y + 55, x + 94, BLUE2)
        rect(x + 96, y + 30, 70, 50, BLUE2, rx=8)
        text(x + 131, y + 52, "EPP", 15, "#FFFFFF", "bold", "middle")
        text(x + 131, y + 69, "score, pick", 11, "#FFFFFF", anchor="middle")
        arrow(x + 168, y + 55, x + 190, BLUE2)
        rw = w - 204
        rect(x + 192, y + 22, rw, 30, TINT_A, rx=6, stroke=BLUE)
        text(x + 192 + rw / 2, y + 42, "replica 1", 12, BLUE, "bold", "middle")
        rect(x + 192, y + 58, rw, 30, "#F9FAFB", rx=6, stroke=LINE, extra='stroke-dasharray="4 3"')
        text(x + 192 + rw / 2, y + 78, "replica 2", 12, "#9CA3AF", anchor="middle")
        text(x + 16, y + h - 12, "1 run per request (was 16)", 12, MUTED)
    elif L["n"] == 5:  # chips like the reference
        for i, (lab, ic) in enumerate([("Pods", "▣"), ("Node + GPU", "▤"), ("Events", "↻")]):
            yy = y + 14 + i * 34
            rect(x + 46, yy, w - 92, 28, "#DCEEFF", rx=6)
            text(x + 66, yy + 19, ic, 15, BLUE, "bold")
            text(x + 92, yy + 19, lab, 14, INK)


def layers():
    gap, x0, y0, cw, ch = 22, 30, 92, (W - 60 - 4 * 22) / 5, 520
    for i, L in enumerate(LAYERS):
        x = x0 + i * (cw + gap)
        rect(x, y0, cw, ch, L["tint"], rx=16)
        icon(L["icon"], x + 18, y0 + 18, L["color"])
        text(x + 74, y0 + 40, f'{L["n"]}. {L["title"]}', 22, L["color"], "bold")
        for j, s in enumerate(L["sub"]):
            text(x + 74, y0 + 64 + j * 20, s, 15, INK)
        illustration(L, x + 14, y0 + 116, cw - 28, 124)
        text(x + 18, y0 + 274, "Key signals", 17, INK, "bold")
        for j, (k, s) in enumerate(L["items"]):
            yy = y0 + 304 + j * 33
            if k == "!":
                add(f'<path d="M{x + 18} {yy + 2}L{x + 26} {yy - 12}L{x + 34} {yy + 2}z" fill="{ORANGE}"/>')
            else:
                add(f'<circle cx="{x + 25}" cy="{yy - 5}" r="5.5" fill="{SIG[k]}"/>')
            text(x + 42, yy, s, 14.5, INK)
        if i < 4:
            arrow(x + cw + 2, y0 + 190, x + cw + gap - 2, "#9CA3AF")
    # legend
    lx = W - 30
    items = [(BLUE, "metric"), (GREEN, "trace"), (ORANGE, "log"), (ORANGE, "misleading")]
    lx -= 4 * 110
    for k, (c, s) in enumerate(items):
        if s == "misleading":
            add(f'<path d="M{lx + k * 110} {72}L{lx + k * 110 + 7} {60}L{lx + k * 110 + 14} {72}z" fill="{c}"/>')
        else:
            add(f'<circle cx="{lx + k * 110 + 7}" cy="66" r="5.5" fill="{c}"/>')
        text(lx + k * 110 + 20, 71, s, 14, MUTED)


def stack():
    y, h = 632, 92
    rect(30, y, W - 60, h, "#F6F8FA", rx=16)
    text(52, y + 40, "Observability", 24, BLUE, "bold")
    text(52, y + 70, "stack", 24, BLUE, "bold")
    boxes = [
        (250, 340, "OpenTelemetry Collector", "the only agent: traces, metrics, logs", "PII redaction, IP masking, sampling", TINT_B, BLUE2),
        (640, 600, "Prometheus  ·  Tempo  ·  Loki", "metrics and SLOs  ·  traces  ·  logs and alerts", "exemplars link a latency dot to its trace", TINT_A, BLUE),
        (1290, 380, "Grafana + Alertmanager", "7 dashboards as code, burn-rate alerts", "tunnel only, never public", TINT_B, BLUE2),
    ]
    for bx, bw, t1, t2, t3, tint, col in boxes:
        rect(bx, y + 10, bw, h - 20, tint, rx=12)
        text(bx + 18, y + 36, t1, 19, col, "bold")
        text(bx + 18, y + 57, t2, 13.5, INK)
        text(bx + 18, y + 74, t3, 12.5, MUTED)
    arrow(596, y + h / 2, 636, BLUE2)
    arrow(1246, y + h / 2, 1286, BLUE2)


def chart(x, y, w, h, title, series, unit, legend=True, ymax=None):
    rect(x, y, w, h, DARK, rx=12)
    text(x + 18, y + 28, title, 15.5, "#FFFFFF", "bold")
    px, py, pw, ph = x + 52, y + 66, w - 72, h - 102
    allv = [v for s in series for _, v in s["points"] if v is not None]
    top = ymax or (max(allv) * 1.15 if allv else 1)
    t0 = min(t for s in series for t, _ in s["points"])
    t1 = max(t for s in series for t, _ in s["points"])
    for k in range(3):
        gy = py + ph - ph * k / 2
        add(f'<line x1="{px}" y1="{gy}" x2="{px + pw}" y2="{gy}" stroke="{DARK_GRID}" stroke-width="1"/>')
        v = top * k / 2
        lab = f"{v:.0f}" if top >= 10 else f"{v:.1f}"
        text(px - 8, gy + 4, lab + unit, 11.5, "#8B949E", anchor="end")
    for m in range(0, int((t1 - t0) / 60) + 1):
        tx = px + pw * (m * 60) / max(1, t1 - t0)
        text(tx, py + ph + 18, f"{m} min", 11.5, "#8B949E", anchor="middle")
    lx = x + 18
    for s in series:
        if legend:
            add(f'<line x1="{lx}" y1="{y + 47}" x2="{lx + 14}" y2="{y + 47}" stroke="{s["color"]}" stroke-width="3"/>')
            text(lx + 19, y + 51, s["name"], 12, DARK_TEXT)
            lx += 7 * len(s["name"]) + 38
        pts = [(px + pw * (t - t0) / max(1, t1 - t0), py + ph - ph * min(v, top) / top) for t, v in s["points"] if v is not None]
        if pts:
            d = "M" + " L".join(f"{a:.1f} {b:.1f}" for a, b in pts)
            if s.get("fill"):
                add(f'<path d="{d} L{pts[-1][0]:.1f} {py + ph} L{pts[0][0]:.1f} {py + ph}z" fill="{s["color"]}" opacity=".15"/>')
            add(f'<path d="{d}" stroke="{s["color"]}" stroke-width="2.5" fill="none" stroke-linejoin="round"/>')


def charts(data):
    y, h, gap = 742, 214, 22
    cw = (W - 60 - 3 * gap) / 4
    cs = data["charts"]
    for i, c in enumerate(cs):
        chart(30 + i * (cw + gap), y, cw, h, c["title"], c["series"], c.get("unit", ""), ymax=c.get("ymax"))
    text(30, H - 22, data["footer"], 13.5, MUTED)


def main():
    data = json.load(open(sys.argv[1]))
    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
    rect(0, 0, W, H, "#FFFFFF", rx=0)
    text(30, 56, "From passport upload to GPU. Observe every layer of an open-weights model.", 32, INK, "bold")
    layers()
    stack()
    charts(data)
    add("</svg>")
    open(sys.argv[2], "w").write("\n".join(out))


main()
