"""One request vs 24 at once, drawn from measured numbers.  python3 scenarios.py scen_metrics.json out.svg"""
import json
import random
import sys
from html import escape

BLUE, BLUE2, TURQ, GREEN, ORANGE = "#0086FF", "#058DC7", "#93EAFF", "#50B432", "#ED561B"
INK, MUTED, LINE, SOFT = "#111827", "#4B5563", "#D0D7DE", "#F6F8FA"
TINT_A, TINT_B, DARK = "#EEF6FF", "#EDFAFE", "#0D1117"
W, H = 1700, 912
F = 'font-family="Arial, Helvetica, sans-serif"'
out = []
add = out.append


def text(x, y, s, size=16, fill=INK, weight="normal", anchor="start"):
    add(f'<text x="{x:.1f}" y="{y:.1f}" {F} font-size="{size}" fill="{fill}" font-weight="{weight}" text-anchor="{anchor}">{escape(s)}</text>')


def rect(x, y, w, h, fill, rx=10, stroke="none", sw=1, extra=""):
    add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" {extra}/>')


def arrow(x1, y, x2, color, width=3):
    add(f'<path d="M{x1} {y}H{x2 - 10}" stroke="{color}" stroke-width="{width}" fill="none"/>'
        f'<path d="M{x2 - 13} {y - 8}L{x2} {y}L{x2 - 13} {y + 8}z" fill="{color}"/>')


one, many = json.load(open(sys.argv[1]))
SPAN = 40.0  # seconds shown on the timelines


def timeline(x, y, w, h, s, lanes):
    rect(x, y, w, h, DARK, rx=12)
    text(x + 18, y + 28, "What the GPU is doing, drawn to scale", 15, "#FFFFFF", "bold")
    px, py, pw, ph = x + 18, y + 46, w - 36, h - 82
    for k in range(0, int(SPAN) + 1, 10):
        gx = px + pw * k / SPAN
        add(f'<line x1="{gx:.1f}" y1="{py}" x2="{gx:.1f}" y2="{py + ph}" stroke="#232B36"/>')
        text(gx, py + ph + 18, f"{k} s", 11.5, "#8B949E", anchor="middle")
    dur, think = s["client_p50"], s["client_ttft_mean"]
    lane_h = ph / 24
    rnd = random.Random(7)
    for i in range(24):
        ly = py + i * lane_h + 1
        if i >= lanes:
            add(f'<rect x="{px:.1f}" y="{ly:.1f}" width="{pw:.1f}" height="{lane_h - 2:.1f}" rx="2" fill="none" stroke="#2B3440" stroke-dasharray="3 4"/>')
            continue
        t = -rnd.uniform(0, dur) if lanes > 1 else 0.4
        while t < SPAN:
            a, m, b = max(t, 0), max(min(t + think, SPAN), 0), min(t + dur, SPAN)
            if m > a:
                rect(px + pw * a / SPAN, ly, pw * (m - a) / SPAN, lane_h - 2, BLUE, rx=2)
            if b > m:
                rect(px + pw * m / SPAN, ly, pw * (b - m) / SPAN, lane_h - 2, GREEN, rx=2)
            t += dur + (0.35 if lanes == 1 else rnd.uniform(0.1, 0.6))
    if lanes == 1:
        text(px + pw / 2, py + ph * .62, "23 of 24 seats idle", 15, "#8B949E", "bold", "middle")
    lx = x + w - 18
    for lab, col in (("answer", GREEN), ("reasoning", BLUE)):
        lx -= 7.2 * len(lab) + 30
        rect(lx, y + 18, 14, 10, col, rx=2)
        text(lx + 19, y + 28, lab, 12, "#C9D1D9")


def tiles(x, y, w, s, other, side):
    data = [
        ("Generated tokens/s", f'{s["gen_tok_s"]:,.0f}', "up"),
        ("Extractions per minute", f'{s["ok_per_min"]:.1f}' if s["ok_per_min"] < 10 else f'{s["ok_per_min"]:.0f}', "up"),
        ("Latency, p50", f'{s["client_p50"]:.1f} s', "down"),
        ("Speed of one request", f'{s["per_req_tok_s"]:.0f} tok/s', "up"),
        ("GPU power", f'{s["power_w"]:.0f} W', "down"),
        ("KV cache used", f'{s["kv_max"] * 100:.1f}%', None),
    ]
    keys = ["gen_tok_s", "ok_per_min", "client_p50", "per_req_tok_s", "power_w", "kv_max"]
    tw, th, gap = (w - 2 * 14) / 3, 92, 14
    for i, ((lab, val, better), k) in enumerate(zip(data, keys)):
        tx, ty = x + (i % 3) * (tw + gap), y + (i // 3) * (th + gap)
        rect(tx, ty, tw, th, "#FFFFFF", rx=10, stroke=LINE)
        col = INK
        if side == "many" and better:
            improved = (s[k] > other[k]) == (better == "up")
            col = GREEN if improved else ORANGE
        text(tx + 16, ty + 30, lab, 13.5, MUTED)
        text(tx + 16, ty + 70, val, 30, col, "bold")


def panel(x, y, w, h, s, title, subtitle, lanes, tint, color, other, side):
    rect(x, y, w, h, tint, rx=18)
    # people icons: 1 vs 24
    for i in range(lanes):
        cx, cy = x + 30 + (i % 12) * 17, y + 30 + (i // 12) * 22
        add(f'<circle cx="{cx}" cy="{cy - 5}" r="4.2" fill="{color}"/><path d="M{cx - 7} {cy + 9}c0-7 3-10 7-10s7 3 7 10z" fill="{color}"/>')
    tx = x + 30 + min(lanes, 12) * 17 + 14
    text(tx, y + 38, title, 27, color, "bold")
    text(tx, y + 62, subtitle, 15, MUTED)
    timeline(x + 22, y + 92, w - 44, 300, s, lanes)
    tiles(x + 22, y + 410, w - 44, s, other, side)


def deltas(x, y, w):
    up = lambda a, b: b / a
    pct = lambda a, b: (b / a - 1) * 100
    rows = [
        (f'{up(one["gen_tok_s"], many["gen_tok_s"]):.1f}×', "tokens per second", GREEN),
        (f'{up(one["ok_per_min"], many["ok_per_min"]):.1f}×', "extractions per minute", GREEN),
        (f'+{pct(one["client_p50"], many["client_p50"]):.0f}%', "latency for each user", ORANGE),
        (f'+{pct(one["power_w"], many["power_w"]):.0f}%', "power draw", ORANGE),
        (f'{one["gpu_util"]:.0f}% → {many["gpu_util"]:.0f}%', "GPU utilization", MUTED),
    ]
    text(x + w / 2, y + 6, "24 at once vs 1", 17, INK, "bold", "middle")
    for i, (big, lab, col) in enumerate(rows):
        yy = y + 30 + i * 98
        rect(x, yy, w, 84, "#FFFFFF", rx=12, stroke=LINE)
        text(x + w / 2, yy + 42, big, 30, col, "bold", "middle")
        text(x + w / 2, yy + 68, lab, 14, MUTED, anchor="middle")


def cost_band(y):
    rect(30, y, W - 60, 120, SOFT, rx=16)
    text(56, y + 44, "What one extraction costs", 22, INK, "bold")
    text(56, y + 72, "Same VM, same $0.87 an hour.", 15, MUTED)
    text(56, y + 94, "Idle seats are what you pay for.", 15, MUTED)
    bx, bw = 420, W - 60 - 420 - 40
    top = one["cost_per_1k_usd"]
    for i, (lab, s, col) in enumerate((("1 request", one, ORANGE), ("24 at once", many, GREEN))):
        yy = y + 26 + i * 44
        text(bx, yy + 21, lab, 15, INK, "bold")
        ww = (bw - 330) * s["cost_per_1k_usd"] / top
        rect(bx + 110, yy, max(ww, 6), 30, col, rx=6)
        text(bx + 110 + max(ww, 6) + 12, yy + 21, f'${s["cost_per_1k_usd"]:.2f} per 1,000 extractions', 16, INK, "bold")
    text(bx + bw, y + 108, f'Energy: {one["tok_per_joule"]:.2f} → {many["tok_per_joule"]:.2f} generated tokens per joule', 13.5, MUTED, anchor="end")


add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
rect(0, 0, W, H, "#FFFFFF", rx=0)
text(30, 56, f'Same GPU, {many["gen_tok_s"] / one["gen_tok_s"]:.1f}× the work: one request vs 24 at once', 32, INK, "bold")
pw = 640
panel(30, 86, pw, 630, one, "1 request at a time", "Each passport waits for the one before", 1, TINT_A, BLUE, many, "one")
panel(W - 30 - pw, 86, pw, 630, many, "24 requests at once", "vLLM batches them on the same GPU", 24, TINT_B, BLUE2, one, "many")
deltas(30 + pw + 34, 110, W - 60 - 2 * pw - 68)
cost_band(736)
fail = many["codes"].get("502", 0)
text(30, H - 26, (f'Measured on this lab, 3 Nov 2026: Qwen3.5-9B FP8 with thinking on, one L40S, the public app path. '
                  f'1 at a time: {one["ok"]} of {one["ok"]} succeeded. 24 at once: {many["ok"]} succeeded and {fail} hit the token cap while reasoning. '
                  f'Nothing waited in the queue in either run.'), 13.5, MUTED)
add("</svg>")
open(sys.argv[2], "w").write("\n".join(out))
