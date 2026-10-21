# Load tests

Two tools, two questions:

| Tool | Path it exercises | Question it answers |
|---|---|---|
| **k6** (`k6/ocr-users.js`) | browser → nginx → API → model | What do many users get? Latency, errors **and correctness**, scored per response against ground truth. |
| **GuideLLM** (`guidellm/run.sh`) | straight to the model server | What can the engine do? TTFT, inter-token latency, throughput, saturation knee. |

The gap between them is the app (and the gateway). That's where the original API concurrency bug
lived: the engine could batch, the API served one request at a time.

## Data

Synthetic passports with ground truth, never real ones:

```bash
python tools/passport-gen/generate.py --count 500 --out loadtest/data/passports
python tools/passport-gen/generate.py --count 200 --hires-fraction 0.4 --out loadtest/data/passports-hires  # prefill experiments
```

12 nationalities, varied names/dates/numbers, four colour schemes, optional watermark, rotation,
blur, noise, JPEG artifacts and resolution from 640 to 1024 px (or up to 2000 px with
`--hires-fraction`). Every MRZ passes ICAO check digits, so a failed check in the API is the model's error.

## k6 scenarios

```bash
k6 run -e BASE_URL=http://<host>/api -e SCENARIO=users -e PEAK_USERS=100 loadtest/k6/ocr-users.js
```

| SCENARIO | Model | Shape |
|---|---|---|
| `smoke` | 1 user, 1 min | sanity check |
| `users` | closed: ramps to `PEAK_USERS`, 1–5 s think time | "many users at once" |
| `rate` | open: steps up to `MAX_RPS` | find the knee |
| `spike` | open: 1 → `SPIKE_RPS` in 10 s | queueing, timeouts, burn-rate alerts |
| `soak` | open: `SOAK_RPS` for `SOAK_MINUTES` | throttling, leaks, budget burn |

Thresholds mirror the SLOs. Custom metrics: `ocr_field_correct`, `ocr_exact_match`, `ocr_mrz_valid`,
token trends. Slow or failed requests are logged with their `trace_id` (k6 starts the trace).
To see runs on the dashboards, send k6 metrics to Prometheus:

```bash
K6_PROMETHEUS_RW_SERVER_URL=http://<prometheus>:9090/api/v1/write \
K6_PROMETHEUS_RW_TREND_STATS="p(50),p(95),p(99)" \
k6 run -o experimental-prometheus-rw --tag testid=$(date +%s) -e SCENARIO=rate ... loadtest/k6/ocr-users.js
```

Run k6 from a machine other than the GPU node so it doesn't compete with the API for CPU.

## GuideLLM

```bash
pip install "guidellm[vision]"
python loadtest/guidellm/make_dataset.py
TARGET=http://<predictor-or-gateway> ./loadtest/guidellm/run.sh sweep
```

Sends the same prompt + image the API sends. Not yet validated end to end against the vision
dataset; try it on the mock model first.
