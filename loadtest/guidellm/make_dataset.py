#!/usr/bin/env python3
"""Turn the passport-gen manifest into a GuideLLM dataset (JSONL).

Each row is one chat request: the API's extraction prompt plus one synthetic
passport image, so GuideLLM sends the model exactly what the app sends, minus
the app. Columns use GuideLLM's default names (prompt, image).

    python loadtest/guidellm/make_dataset.py --data loadtest/data/passports --out loadtest/data/guidellm.jsonl
"""
import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "apps" / "api"))
from app.ocr import PROMPT  # noqa: E402  (single source of truth for the prompt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="loadtest/data/passports")
    ap.add_argument("--out", default="loadtest/data/guidellm.jsonl")
    args = ap.parse_args()
    data = pathlib.Path(args.data).resolve()
    rows = 0
    with open(args.out, "w") as out:
        for line in open(data / "manifest.jsonl"):
            rec = json.loads(line)
            out.write(json.dumps({"prompt": PROMPT, "image": str(data / rec["file"]),
                                  "output_tokens_count": 160}) + "\n")
            rows += 1
    print(f"wrote {rows} rows to {args.out}")


if __name__ == "__main__":
    main()
