#!/usr/bin/env bash
# Install the OCR lab's observability stack into the cluster (namespace: monitoring).
#
#   1. kube-prometheus-stack  Prometheus (OTLP receiver + exemplars), Alertmanager, Grafana, node-exporter, kube-state-metrics
#   2. Loki                   logs (OTLP), single binary
#   3. Tempo                  traces (OTLP), span metrics + service graph -> Prometheus
#   4. ocr-observability      collector config, PodMonitors, SLO/cost rules, dashboards (charts/observability)
#   5. OTel Collector         DaemonSet: OTLP gateway + pod logs + Kubernetes events, PII + cardinality guards
#   6. DCGM exporter          GPU metrics (skipped with GPU=false)
#
# Idempotent. Run with KUBECONFIG pointing at the lab cluster:
#   KUBECONFIG=~/.kube/ocr-lab.config ./observability/install.sh
#   GPU=false ./observability/install.sh          # no GPU node yet (mock model)
#   SCRAPE="--set scrape.llmisvcVllm.enabled=true --set scrape.llmdScheduler.enabled=true" ./observability/install.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NS="${NS:-monitoring}"
GPU="${GPU:-true}"
SCRAPE="${SCRAPE:-}"
V="$REPO_ROOT/observability/values"

# Chart versions verified together (2026-10). Bump deliberately.
KPS_VERSION="${KPS_VERSION:-92.11.0}"
LOKI_VERSION="${LOKI_VERSION:-7.3.0}"
TEMPO_VERSION="${TEMPO_VERSION:-3.2.0}"
OTELCOL_VERSION="${OTELCOL_VERSION:-0.176.1}"
DCGM_VERSION="${DCGM_VERSION:-}"   # empty = latest from NVIDIA's repo

log() { echo "[observability] $*"; }
require() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 1; }; }
require kubectl
require helm
ver() { [[ -n "$1" ]] && echo "--version $1"; }

log "Adding Helm repos..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts >/dev/null 2>&1 || true
helm repo add grafana https://grafana.github.io/helm-charts >/dev/null 2>&1 || true
helm repo add grafana-community https://grafana-community.github.io/helm-charts >/dev/null 2>&1 || true
helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts >/dev/null 2>&1 || true
helm repo add nvidia-dcgm https://nvidia.github.io/dcgm-exporter/helm-charts >/dev/null 2>&1 || true
helm repo update >/dev/null

kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -

log "1/6 kube-prometheus-stack ${KPS_VERSION}"
helm upgrade --install kps prometheus-community/kube-prometheus-stack -n "$NS" \
  --version "$KPS_VERSION" -f "$V/kube-prometheus-stack.yaml" --wait --timeout 10m

log "2/6 Loki ${LOKI_VERSION}"
helm upgrade --install loki grafana/loki -n "$NS" \
  --version "$LOKI_VERSION" -f "$V/loki.yaml" --wait --timeout 10m

log "3/6 Tempo ${TEMPO_VERSION}"
helm upgrade --install tempo grafana-community/tempo -n "$NS" \
  --version "$TEMPO_VERSION" -f "$V/tempo.yaml" --wait --timeout 10m

log "4/6 ocr-observability (collector config, scrape targets, rules, dashboards)"
# shellcheck disable=SC2086
helm upgrade --install ocr-observability "$REPO_ROOT/charts/observability" -n "$NS" $SCRAPE

log "5/6 OpenTelemetry Collector ${OTELCOL_VERSION}"
helm upgrade --install otel-collector open-telemetry/opentelemetry-collector -n "$NS" \
  --version "$OTELCOL_VERSION" -f "$V/otel-collector.yaml" --wait --timeout 5m
# Pick up collector config changes from the ConfigMap.
kubectl -n "$NS" rollout restart daemonset -l app.kubernetes.io/instance=otel-collector >/dev/null

if [[ "$GPU" == "true" ]]; then
  log "6/6 DCGM exporter ${DCGM_VERSION:-latest}"
  # shellcheck disable=SC2046
  helm upgrade --install dcgm-exporter nvidia-dcgm/dcgm-exporter -n "$NS" $(ver "$DCGM_VERSION") \
    -f "$V/dcgm-exporter.yaml" --wait --timeout 5m
else
  log "6/6 GPU=false — skipping DCGM exporter"
fi

log "Done. Grafana: kubectl -n $NS port-forward svc/kps-grafana 3000:80  (admin / see values)"
log "Apps send OTLP to http://otel-collector-opentelemetry-collector.$NS.svc:4318"
