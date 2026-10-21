# mock-llm

A fake vLLM for running the OCR lab's observability stack without a GPU. It speaks the
OpenAI chat-completions API (streaming and non-streaming), simulates queueing, prefill
and decode, exposes a subset of vLLM's `vllm:*` Prometheus metrics with the real names,
and continues the caller's W3C trace with an `llm_request` span.

It answers with the ground truth that `tools/passport-gen` embeds in each PNG, corrupted
at configurable rates, so the MRZ-validity and field-accuracy SLIs move as they would
with a real model.

**Its latency numbers are illustrative. Never present mock runs as GPU results.**

| Env | Default | Meaning |
|---|---|---|
| `MOCK_MAX_NUM_SEQS` | 16 | Concurrent sequences before requests queue |
| `MOCK_PREFILL_MS_PER_TOKEN` | 0.35 | Prefill cost per prompt token (image tokens = one per 32×32 px) |
| `MOCK_DECODE_MS_PER_TOKEN` | 14 | Decode cost per output token at batch size 1 |
| `MOCK_BATCH_SLOWDOWN` | 0.04 | Extra cost per running sequence |
| `MOCK_KV_CAPACITY_TOKENS` | 60000 | Denominator for `vllm:kv_cache_usage_perc` |
| `MOCK_STARTUP_SECONDS` | 0 | Simulated model-load time; `/health` returns 503 until it passes |
| `MOCK_FIELD_ERROR_RATE` | 0.03 | Chance to corrupt one character of a visual-zone field |
| `MOCK_MRZ_ERROR_RATE` | 0.01 | Chance to corrupt MRZ line 2 (fails check digits) |
| `MOCK_JSON_ERROR_RATE` | 0.005 | Chance to return truncated JSON |

Deployed by `charts/mock-model`.
