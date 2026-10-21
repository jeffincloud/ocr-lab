#!/usr/bin/env python3
"""Generate synthetic, ICAO 9303 TD3-style passport images with ground truth.

Every image is fictional: random names, numbers and dates, a "SPECIMEN"
style layout and no real person's data. Each PNG carries its ground truth in a
tEXt chunk ("ocr_truth") and a manifest.jsonl lists file -> truth, so load
tests can score field accuracy and the mock model can answer correctly.

Variety is deliberate, so the model doesn't see the same request every time:
names and nationalities from several regions, random dates and document
numbers, several layouts and colour schemes, and image degradation (rotation,
blur, noise, contrast, JPEG artifacts, resolution).

    python tools/passport-gen/generate.py --count 500 --out loadtest/data/passports
    python tools/passport-gen/generate.py --count 100 --hires-fraction 0.3 ...

Images wider than the API's MAX_IMAGE_DIM (1024) get re-encoded by the API,
which drops the tEXt chunk; the manifest still has their truth.
"""
import argparse
import datetime as dt
import io
import json
import math
import pathlib
import random

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from PIL.PngImagePlugin import PngInfo

# (ISO 3166-1 alpha-3, country name, surnames, given names). Fictional
# combinations; names are common and ASCII so the MRZ needs no transliteration.
REGIONS = [
    ("UTO", "UTOPIA", ["ERIKSSON", "LINDQVIST", "BERG", "NYSTROM"], ["ANNA", "MARIA", "ERIK", "LARS", "INGRID"]),
    ("COL", "COLOMBIA", ["GARCIA", "RODRIGUEZ", "MARTINEZ", "LOPEZ", "GOMEZ"], ["JUAN", "CARLOS", "VALENTINA", "SOFIA", "ANDRES"]),
    ("MEX", "MEXICO", ["HERNANDEZ", "GONZALEZ", "PEREZ", "SANCHEZ"], ["JOSE", "LUIS", "GUADALUPE", "FERNANDA", "DIEGO"]),
    ("USA", "UNITED STATES OF AMERICA", ["SMITH", "JOHNSON", "WILLIAMS", "BROWN", "MILLER"], ["JAMES", "MARY", "ROBERT", "PATRICIA", "OLIVIA"]),
    ("CAN", "CANADA", ["TREMBLAY", "ROY", "MACDONALD", "WILSON"], ["NOAH", "EMMA", "LIAM", "CHARLOTTE"]),
    ("AUT", "AUSTRIA", ["GRUBER", "HUBER", "WAGNER", "PICHLER"], ["LUKAS", "LEONIE", "FELIX", "HANNA"]),
    ("FRA", "FRANCE", ["MARTIN", "BERNARD", "DUBOIS", "THOMAS"], ["LOUIS", "CHLOE", "HUGO", "MANON"]),
    ("JPN", "JAPAN", ["SATO", "SUZUKI", "TAKAHASHI", "TANAKA"], ["HARUTO", "YUI", "SOTA", "HINA"]),
    ("IND", "INDIA", ["SHARMA", "PATEL", "SINGH", "KUMAR"], ["AARAV", "ANANYA", "VIVAAN", "DIYA"]),
    ("NGA", "NIGERIA", ["OKAFOR", "ADEYEMI", "BELLO", "EZE"], ["CHIDI", "AMARA", "TUNDE", "NGOZI"]),
    ("BRA", "BRAZIL", ["SILVA", "SANTOS", "OLIVEIRA", "SOUZA"], ["GABRIEL", "ALICE", "MIGUEL", "HELENA"]),
    ("KOR", "REPUBLIC OF KOREA", ["KIM", "LEE", "PARK", "CHOI"], ["MINJUN", "SEOYEON", "JIHO", "HAYUN"]),
]
THEMES = [  # (paper, ink, accent)
    ((236, 232, 220), (25, 25, 35), (120, 20, 40)),
    ((225, 236, 230), (20, 30, 25), (20, 90, 60)),
    ((228, 232, 242), (20, 25, 45), (30, 50, 120)),
    ((242, 236, 226), (40, 30, 20), (140, 90, 20)),
]
FONT_DIRS = ["/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation",
             "/Library/Fonts", "/System/Library/Fonts/Supplemental"]


def _font(names, size):
    for d in FONT_DIRS:
        for n in names:
            p = pathlib.Path(d) / n
            if p.exists():
                return ImageFont.truetype(str(p), size)
    return ImageFont.load_default(size)


SANS = ["DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Arial.ttf"]
SANS_BOLD = ["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "Arial Bold.ttf"]
MONO = ["DejaVuSansMono.ttf", "LiberationMono-Regular.ttf", "Courier New.ttf"]

# --- ICAO 9303 ---------------------------------------------------------------


def check_digit(s: str) -> str:
    total = 0
    for i, ch in enumerate(s):
        if ch.isdigit():
            v = int(ch)
        elif ch.isalpha():
            v = ord(ch) - 55
        else:
            v = 0
        total += v * (7, 3, 1)[i % 3]
    return str(total % 10)


def mrz_td3(issuer, surname, given, number, nationality, dob, sex, expiry, personal):
    name = f"{surname}<<{given.replace(' ', '<')}"
    line1 = f"P<{issuer}{name}"[:44].ljust(44, "<")
    num = number.ljust(9, "<")
    pers = personal.ljust(14, "<")
    dob_s, exp_s = dob.strftime("%y%m%d"), expiry.strftime("%y%m%d")
    parts = [num + check_digit(num), dob_s + check_digit(dob_s), exp_s + check_digit(exp_s),
             pers + check_digit(pers)]
    composite = check_digit(parts[0] + parts[1] + parts[2] + parts[3])
    line2 = f"{parts[0]}{nationality}{parts[1]}{sex}{parts[2]}{parts[3]}{composite}"
    return line1, line2


# --- Document ----------------------------------------------------------------


def random_person(rng: random.Random) -> dict:
    code, country, surnames, givens = rng.choice(REGIONS)
    given = " ".join(rng.sample(givens, rng.choice([1, 1, 2])))
    surname = rng.choice(surnames)
    if rng.random() < 0.2:
        surname = f"{surname} {rng.choice(surnames)}"
    today = dt.date.today()
    dob = today - dt.timedelta(days=rng.randint(18 * 365, 85 * 365))
    issue = today - dt.timedelta(days=rng.randint(30, 9 * 365))
    expiry = issue.replace(year=issue.year + 10) - dt.timedelta(days=1) if not (issue.month == 2 and issue.day == 29) \
        else dt.date(issue.year + 10, 2, 28)
    number = rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") + "".join(rng.choice("0123456789") for _ in range(rng.choice([7, 8])))
    personal = "".join(rng.choice("0123456789") for _ in range(rng.choice([0, 0, 10])))
    sex = rng.choice("MF")
    l1, l2 = mrz_td3(code, surname.replace(" ", "<"), given, number, code, dob, sex, expiry, personal)
    return {
        "_country": country,
        "surname": surname,
        "given_names": given,
        "passport_number": number,
        "nationality": code,
        "date_of_birth": dob.isoformat(),
        "sex": sex,
        "date_of_issue": issue.isoformat(),
        "date_of_expiry": expiry.isoformat(),
        "issuing_authority": rng.choice(["MINISTRY OF FOREIGN AFFAIRS", "PASSPORT OFFICE", "DEPARTMENT OF STATE",
                                         "NATIONAL REGISTRY", f"CONSULATE GENERAL {rng.choice(['MADRID', 'TORONTO', 'TOKYO'])}"]),
        "mrz_line1": l1,
        "mrz_line2": l2,
    }


def _fmt_date(iso: str, style: int) -> str:
    d = dt.date.fromisoformat(iso)
    return [d.strftime("%d %b %Y").upper(), d.strftime("%d/%m/%Y"), d.strftime("%d %b/%b %y").upper()][style]


def render(p: dict, rng: random.Random) -> Image.Image:
    W, H = 1250, 880
    paper, ink, accent = rng.choice(THEMES)
    img = Image.new("RGB", (W, H), paper)
    d = ImageDraw.Draw(img)

    # Guilloche-ish background lines.
    for k in range(18):
        amp, freq, y0 = rng.randint(8, 30), rng.uniform(0.006, 0.02), rng.randint(0, H)
        pts = [(x, y0 + amp * math.sin(freq * x + k)) for x in range(0, W, 6)]
        d.line(pts, fill=tuple(min(255, c + 12) if i != 2 else max(0, c - 10) for i, c in enumerate(paper)), width=1)

    big, label, value = _font(SANS_BOLD, 38), _font(SANS, 18), _font(SANS_BOLD, 28)
    d.text((40, 30), p["_country"], font=big, fill=accent)
    d.text((40, 80), "PASSPORT / PASSEPORT / PASAPORTE", font=label, fill=accent)
    d.text((W - 260, 40), f"P   {p['nationality']}", font=value, fill=ink)

    # Photo placeholder with a silhouette (no faces).
    px, py, pw, ph = 50, 140, 300, 390
    d.rectangle((px, py, px + pw, py + ph), fill=tuple(c - 25 for c in paper), outline=ink, width=2)
    d.ellipse((px + 95, py + 70, px + 205, py + 190), fill=tuple(c - 60 for c in paper))
    d.ellipse((px + 50, py + 200, px + 250, py + 420), fill=tuple(c - 60 for c in paper))

    style = rng.randrange(3)
    rows = [("Surname / Nom / Apellidos", p["surname"]),
            ("Given names / Prénoms / Nombres", p["given_names"]),
            ("Nationality / Nationalité", p["_country"]),
            ("Date of birth / Date de naissance", _fmt_date(p["date_of_birth"], style)),
            ("Sex / Sexe", p["sex"]),
            ("Date of issue / Date de délivrance", _fmt_date(p["date_of_issue"], style)),
            ("Date of expiry / Date d'expiration", _fmt_date(p["date_of_expiry"], style)),
            ("Authority / Autorité", p["issuing_authority"])]
    x, y = 400, 140
    for i, (lab, val) in enumerate(rows):
        if i == 4:  # sex and passport number share a row
            d.text((x, y), lab, font=label, fill=ink)
            d.text((x, y + 22), val, font=value, fill=ink)
            d.text((x + 400, y), "Passport No. / No. du passeport", font=label, fill=ink)
            d.text((x + 400, y + 22), p["passport_number"], font=value, fill=ink)
        else:
            d.text((x, y), lab, font=label, fill=ink)
            d.text((x, y + 22), val, font=value, fill=ink)
        y += 62

    if rng.random() < 0.5:  # watermark the prompt tells the model to ignore
        wm = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(wm).text((300, 330), "SPECIMEN", font=_font(SANS_BOLD, 150), fill=accent + (40,))
        img = Image.alpha_composite(img.convert("RGBA"), wm.rotate(rng.uniform(-20, 20))).convert("RGB")
        d = ImageDraw.Draw(img)

    d.rectangle((0, H - 170, W, H), fill=tuple(min(255, c + 8) for c in paper))
    mono = _font(MONO, 40)
    d.text((40, H - 150), p["mrz_line1"], font=mono, fill=ink)
    d.text((40, H - 85), p["mrz_line2"], font=mono, fill=ink)
    return img


def degrade(img: Image.Image, rng: random.Random, max_dim: int) -> Image.Image:
    img = img.rotate(rng.uniform(-3, 3), expand=True, fillcolor=(rng.randint(60, 200),) * 3,
                     resample=Image.BICUBIC)
    img = ImageEnhance.Contrast(img).enhance(rng.uniform(0.7, 1.2))
    img = ImageEnhance.Brightness(img).enhance(rng.uniform(0.8, 1.15))
    if rng.random() < 0.5:
        img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 1.4)))
    if rng.random() < 0.4:
        noise = Image.effect_noise(img.size, rng.uniform(8, 25)).convert("RGB")
        img = Image.blend(img, noise, rng.uniform(0.04, 0.12))
    if rng.random() < 0.4:  # JPEG artifacts, then back to PNG to keep the tEXt chunk
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=rng.randint(35, 75))
        img = Image.open(io.BytesIO(buf.getvalue())).convert("RGB")
    scale = max_dim / max(img.size)
    return img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--count", type=int, default=200)
    ap.add_argument("--out", default="loadtest/data/passports")
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--min-dim", type=int, default=640, help="smallest longest-side in px")
    ap.add_argument("--max-dim", type=int, default=1024, help="largest longest-side in px")
    ap.add_argument("--hires-fraction", type=float, default=0.0,
                    help="share of images rendered at 1400-2000 px (prefill-cost experiments)")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "manifest.jsonl", "w") as manifest:
        for i in range(args.count):
            person = random_person(rng)
            truth = {k: v for k, v in person.items() if not k.startswith("_")}
            hires = rng.random() < args.hires_fraction
            dim = rng.randint(1400, 2000) if hires else rng.randint(args.min_dim, args.max_dim)
            img = degrade(render(person, rng), rng, dim)
            meta = PngInfo()
            meta.add_text("ocr_truth", json.dumps(truth))
            name = f"passport-{i:05d}.png"
            img.save(out / name, pnginfo=meta, optimize=False)
            manifest.write(json.dumps({"file": name, "width": img.width, "height": img.height,
                                       "truth": truth}) + "\n")
    print(f"wrote {args.count} images and manifest.jsonl to {out}")


if __name__ == "__main__":
    main()
