# OCR Frontend

Static upload form that posts a passport image to the API and renders the
extracted fields. Plain HTML + vanilla JS; no build step.

Served in production by nginx, which also reverse-proxies `/api/*` to the
`ocr-api` service.

## Local dev — option A: nginx in Docker

```bash
# Assumes the API is running on host port 8080 (see apps/api/README.md)
docker build -t ocr-frontend apps/frontend
docker run --rm -p 3000:80 \
  -e API_HOST=host.docker.internal -e API_PORT=8080 \
  ocr-frontend
# open http://localhost:3000
```

## Local dev — option B: static server + direct API

No Docker, fastest iteration. Needs `ALLOWED_ORIGINS` set on the API.

```bash
# terminal 1 — API with CORS
cd apps/api
ALLOWED_ORIGINS=http://localhost:3000 MAX_IMAGE_DIM=1536 \
  ../../.venv/bin/uvicorn app.main:app --port 8080

# terminal 2 — frontend
python3 -m http.server 3000 --directory apps/frontend/public
# open http://localhost:3000?apiBase=http://localhost:8080
```

The `?apiBase=...` query parameter is persisted in `localStorage`, so subsequent
visits don't need it.
