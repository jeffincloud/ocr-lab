import ollama, json, sys

PROMPT = """You are an OCR system for passports. Extract the passport holder's data from the image.

Return ONLY a JSON object with these keys (use null if not visible):
- surname: family name as printed in the NAME/SURNAME field (NOT text from watermarks or the country header)
- given_names: first and middle names
- passport_number
- nationality
- date_of_birth (format: YYYY-MM-DD)
- sex (M or F)
- date_of_issue (format: YYYY-MM-DD)
- date_of_expiry (format: YYYY-MM-DD)
- issuing_authority
- mrz_line1
- mrz_line2

Ignore any watermarks, holograms, or specimen text. Return JSON only."""

def extract(image_path: str) -> dict:
    r = ollama.generate(
        model="qwen3-vl:4b",
        prompt=PROMPT,
        images=[image_path],
        format="json",
        think=False,
        options={"temperature": 0, "num_predict": 1024},
    )
    payload = r.get("response") or r.get("thinking") or ""
    return json.loads(payload)

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "tests/fixtures/passports/passport1.png"
    print(json.dumps(extract(path), indent=2, ensure_ascii=False))
