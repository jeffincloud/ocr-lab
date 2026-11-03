"""Thinking on vs off on the same 40 passports.  python3 think_img.py out.svg"""
import sys
from html import escape

BLUE, BLUE2, TURQ, GREEN, ORANGE = "#0086FF", "#058DC7", "#93EAFF", "#50B432", "#ED561B"
INK, MUTED, LINE, SOFT = "#111827", "#4B5563", "#D0D7DE", "#F6F8FA"
TINT_A, TINT_B, DARK, DT = "#EEF6FF", "#EDFAFE", "#0D1117", "#C9D1D9"
W, H = 1700, 1060
F = 'font-family="Arial, Helvetica, sans-serif"'
MONO = 'font-family="Consolas, Menlo, monospace"'
out = []
add = out.append


def text(x, y, s, size=16, fill=INK, weight="normal", anchor="start", font=F):
    add(f'<text x="{x:.1f}" y="{y:.1f}" {font} font-size="{size}" fill="{fill}" font-weight="{weight}" text-anchor="{anchor}">{escape(s)}</text>')


def rect(x, y, w, h, fill, rx=10, stroke="none", sw=1):
    add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}"/>')


# Measured: 40 synthetic passports each, 8 at a time, public app path, 3 Nov 2026.
ON = dict(p50=14.1, ttft=10.0, decode=14.1, out_tok=645, reason_tok=476, answer_tok=175, answered=37, wrong=0, checked=259,
          correct_docs=37, mrz=(33, 37), per_min=25.5, cost=0.57, wall=87)
OFF = dict(p50=5.2, ttft=0.12, decode=4.0, out_tok=203, reason_tok=0, answer_tok=198, answered=40, wrong=2, checked=280,
           correct_docs=38, mrz=(35, 40), per_min=78.6, cost=0.18, wall=29)

add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">')
rect(0, 0, W, H, "#FFFFFF", rx=0)
text(30, 56, "Thinking on vs off: same 40 passports, same model, same GPU", 32, INK, "bold")
text(30, 86, "Qwen3.5-9B FP8 on one L40S, 8 passports at a time through the public app. The only change is enable_thinking.", 16, MUTED)

# --- 1. one request, to scale ----------------------------------------------------------
y0 = 112
rect(30, y0, W - 60, 232, DARK, rx=14)
text(52, y0 + 34, "One passport, drawn to scale", 17, "#FFFFFF", "bold")
px, pw, span = 250, W - 60 - 250 - 40, 15.0
sx = lambda t: px + pw * t / span
for k in range(0, 16, 5):
    add(f'<line x1="{sx(k):.1f}" y1="{y0 + 54}" x2="{sx(k):.1f}" y2="{y0 + 196}" stroke="#232B36"/>')
    text(sx(k), y0 + 216, f"{k} s", 12, "#8B949E", anchor="middle")
rows = [("Thinking on", BLUE, ON, y0 + 70), ("Thinking off", TURQ, OFF, y0 + 140)]
for lab, col, s, yy in rows:
    text(52, yy + 26, lab, 18, col, "bold")
    t_first = s["ttft"]
    if s["reason_tok"]:
        rect(sx(0.1), yy, sx(t_first) - sx(0.1), 40, BLUE, rx=4)
        text(sx(0.1) + 14, yy + 26, f'reasoning: {s["reason_tok"]} tokens the user never sees', 15, "#FFFFFF", "bold")
    rect(sx(t_first), yy, sx(s["p50"]) - sx(t_first), 40, GREEN, rx=4)
    text(sx(t_first) + 12, yy + 26, f'answer: {s["answer_tok"]} tokens', 15, DARK, "bold")
    add(f'<line x1="{sx(t_first):.1f}" y1="{yy - 6}" x2="{sx(t_first):.1f}" y2="{yy + 46}" stroke="#FFFFFF" stroke-width="2" stroke-dasharray="4 3"/>')
    text(sx(s["p50"]) + 12, yy + 26, f'{s["p50"]:.1f} s', 18, "#FFFFFF", "bold")
text(sx(ON["ttft"]), y0 + 62, f'first content at {ON["ttft"]:.1f} s', 12.5, DT, anchor="middle")
text(sx(OFF["ttft"]) + 6, y0 + 196, f'first content at {OFF["ttft"]:.2f} s', 12.5, DT)

# --- 2. what the model writes ------------------------------------------------------------
y1 = 364
cw = (W - 60 - 24) / 2
text(30, y1 + 20, "What the model writes for passport 22 (fictional data). Printed issue date: 31 AUG 19.", 17, INK, "bold")
cards = [
    ("Thinking on: reasoning, then JSON", BLUE, [
        ("5. Date of Birth: \"10 MAR 43\" ... So, 1943-03-10.", DT),
        ("7. Date of Issue: \"31 AUG 19\". This implies 1919.", ORANGE),
        ("8. Date of Expiry: \"30 AUG 29\". This implies 1929.", ORANGE),
        ("Now I will format this into the requested JSON.", DT),
        ('{"date_of_issue": "1919-08-31", ...}', TURQ),
    ], "Visible reasoning shows why it went wrong. In the batch the same", "passport came back right (2019): reasoning varies between runs."),
    ("Thinking off: JSON straight away", BLUE2, [
        ("{", DT),
        ('  "date_of_birth": "1943-03-10",', DT),
        ('  "date_of_issue": "1919-08-31",', ORANGE),
        ('  "date_of_expiry": "1929-08-30",', ORANGE),
        ("  ...}", DT),
    ], "Same mistake, no explanation. The MRZ check-digit step corrected", "the expiry to 2029; the issue date isn't in the MRZ, so it stayed wrong."),
]
for i, (title, col, lines, n1, n2) in enumerate(cards):
    x = 30 + i * (cw + 24)
    rect(x, y1 + 36, cw, 232, TINT_A if i == 0 else TINT_B, rx=14)
    text(x + 20, y1 + 66, title, 17, col, "bold")
    rect(x + 20, y1 + 80, cw - 40, 130, DARK, rx=10)
    for j, (ln, c) in enumerate(lines):
        text(x + 36, y1 + 106 + j * 23, ln, 14, c, font=MONO)
    text(x + 20, y1 + 234, n1, 13.5, MUTED)
    text(x + 20, y1 + 254, n2, 13.5, MUTED)

# --- 3. the batch ------------------------------------------------------------------------
y2 = 652
text(30, y2 + 20, "The whole batch: 40 passports each", 17, INK, "bold")
metrics = [
    ("Latency, p50", f'{ON["p50"]:.1f} s', f'{OFF["p50"]:.1f} s', "off"),
    ("First content", f'{ON["ttft"]:.1f} s', f'{OFF["ttft"]:.2f} s', "off"),
    ("Output tokens", f'{ON["out_tok"]}', f'{OFF["out_tok"]}', "off"),
    ("Answered", f'{ON["answered"]}/40', f'{OFF["answered"]}/40', "off"),
    ("Wrong fields", f'{ON["wrong"]} of {ON["checked"]}', f'{OFF["wrong"]} of {OFF["checked"]}', "on"),
    ("Fully correct", f'{ON["correct_docs"]}/40', f'{OFF["correct_docs"]}/40', "off"),
    ("Per 1,000", f'${ON["cost"]:.2f}', f'${OFF["cost"]:.2f}', "off"),
]
tw, gap = (W - 60 - 6 * 14) / 7, 14
for i, (lab, von, voff, win) in enumerate(metrics):
    x = 30 + i * (tw + gap)
    rect(x, y2 + 36, tw, 158, "#FFFFFF", rx=12, stroke=LINE)
    text(x + 16, y2 + 64, lab, 14.5, MUTED, "bold")
    for j, (who, v, col) in enumerate((("on", von, BLUE), ("off", voff, BLUE2))):
        yy = y2 + 104 + j * 60
        text(x + 16, yy - 18, f"thinking {who}", 12, col, "bold")
        good = (win == who)
        text(x + 16, yy + 12, v, 25, GREEN if good else INK, "bold")
text(30, y2 + 222, "Green marks the better result. Wrong fields leave out nationality: both modes sometimes write the country name instead of the code, which is a format choice and not a misread.", 13.5, MUTED)

# --- 4. takeaway -------------------------------------------------------------------------
y3 = 900
rect(30, y3, W - 60, 110, SOFT, rx=16)
text(56, y3 + 40, "What thinking bought: zero misread fields on every passport it answered.", 19, INK, "bold")
text(56, y3 + 68, "What it cost: 2.7× the latency, 3.2× the tokens, 10 s before the first character, and 3 of 40 passports with no answer at all", 15.5, MUTED)
text(56, y3 + 90, "(reasoning ran into the 1,500-token cap). On this batch, thinking off delivered 3× more fully correct passports per minute.", 15.5, MUTED)
text(30, H - 22, "An earlier batch of 40 from the same generator (rotation, blur, noise) went harder against thinking off: 13 wrong fields of 320, against 0 with it on. Measured 3 Nov 2026.", 13.5, MUTED)
add("</svg>")
open(sys.argv[1], "w").write("\n".join(out))
