# vLLM with the OpenTelemetry packages its tracing needs.
#
# Only for the legacy charts/model path (vLLM v0.11). vLLM >= v0.31 (charts/model-llmd)
# ships these packages, so the upstream image traces as is.
#
# vLLM's --otlp-traces-endpoint only works when opentelemetry-sdk and an OTLP
# exporter are importable; the upstream vllm-openai image doesn't list them as
# requirements. This adds them without changing anything else.
#
#   docker build -t ghcr.io/<you>/vllm-openai-otel:v0.11.0 --build-arg VLLM_TAG=v0.11.0 apps/vllm-otel
ARG VLLM_TAG=v0.11.0
FROM vllm/vllm-openai:${VLLM_TAG}
RUN pip install --no-cache-dir \
      "opentelemetry-sdk>=1.26,<2" \
      "opentelemetry-api>=1.26,<2" \
      "opentelemetry-exporter-otlp-proto-grpc>=1.26,<2" \
      "opentelemetry-semantic-conventions-ai>=0.4.1"
