#!/usr/bin/env bash
# Benchmark the model server directly with GuideLLM (no app in the path).
#
# k6 (loadtest/k6) measures what users get through nginx -> API -> model.
# GuideLLM measures only the engine: TTFT, inter-token latency and throughput
# at increasing load, and finds the knee. The gap between the two is the app.
#
# Usage:
#   python loadtest/guidellm/make_dataset.py            # passports -> JSONL with image + prompt
#   TARGET=http://<predictor-or-gateway> ./loadtest/guidellm/run.sh [sweep|concurrent|knee]
#
# Needs: pip install "guidellm[vision]" (tested CLI syntax: guidellm 0.8.x).
# NOTE: not yet validated end to end against the vision dataset; run it once
# against the mock model first (TARGET=http://localhost:9000).
set -euo pipefail

TARGET="${TARGET:-http://localhost:8080}"
MODEL="${MODEL:-qwen3-5-9b}"
DATA="${DATA:-loadtest/data/guidellm.jsonl}"
MODE="${1:-sweep}"
DURATION="${DURATION:-120}"
OUT="${OUT:-loadtest/results/guidellm-${MODE}-$(date +%Y%m%d-%H%M%S)}"

common=(
  --backend "kind=openai_http,target=${TARGET},model=${MODEL},request_format=/v1/chat/completions"
  --data "kind=json_file,path=${DATA}"
  --data-preprocessor kind=encode_media
  --constraint "kind=max_duration,seconds=${DURATION}"
  --output "kind=json,path=${OUT}.json"
  --output "kind=html,path=${OUT}.html"
  --label "run=${MODE}"
)

case "$MODE" in
  # Synchronous baseline, max throughput, then rates in between: the classic capacity curve.
  sweep)      guidellm run "${common[@]}" --profile kind=sweep ;;
  # Fixed concurrency levels, comparable with k6's virtual users.
  concurrent) guidellm run "${common[@]}" --profile kind=concurrent --override profile.streams 1,2,4,8,16,32 ;;
  # Let GuideLLM search for the saturation knee.
  knee)       guidellm run "${common[@]}" --profile kind=knee ;;
  *) echo "unknown mode: $MODE (sweep|concurrent|knee)" >&2; exit 1 ;;
esac
echo "results: ${OUT}.json / ${OUT}.html"
