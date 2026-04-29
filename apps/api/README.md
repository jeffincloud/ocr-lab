# OCR API

FastAPI service that accepts a passport image upload and returns structured JSON.

## Local dev

```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export MODEL_ENDPOINT=http://localhost:11434/api/generate
export MODEL_NAME=qwen3-vl:4b
uvicorn app.main:app --reload --port 8080
```

Then:

```bash
curl -F "file=@../../tests/fixtures/passports/passport1.png" http://localhost:8080/extract
```

## Scripts

- `scripts/test_ollama_local.py` — direct Ollama call, no FastAPI. Used during
  prompt iteration.
