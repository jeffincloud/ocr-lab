#!/usr/bin/env bash
# Install KServe with the LLMInferenceService (llm-d) integration and Gateway API.
#
# Uses KServe's own pinned quick-install scripts from the release tag, which
# bring in: cert-manager, Gateway API CRDs, Gateway API Inference Extension
# CRDs (InferencePool), Envoy Gateway + Envoy AI Gateway, a GatewayClass and
# Gateway, LeaderWorkerSet, and the KServe controllers.
#
# This replaces the KServe v0.14 install from install-cluster-deps.sh on the
# new instance: run install-cluster-deps.sh with SKIP_KSERVE=true (device
# plugin + cert-manager only), then this script. Both the plain
# InferenceService path (charts/model) and the llm-d path (charts/model-llmd)
# then run on KServe v0.21.
#
# On K3s: install with --disable=traefik so Envoy Gateway can take ports 80/443,
# and expose the frontend through the same Gateway (charts/frontend
# httpRoute.enabled=true). One Gateway API entry point for app and model.
#
# NOTE: not yet run on the lab's GPU node.
#
#   KUBECONFIG=~/.kube/ocr-lab.config ./scripts/install-llmisvc.sh
set -euo pipefail

KSERVE_VERSION="${KSERVE_VERSION:-v0.21.0}"
BASE="https://raw.githubusercontent.com/kserve/kserve/${KSERVE_VERSION}/hack/setup/quick-install"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

log() { echo "[install-llmisvc] $*"; }
command -v kubectl >/dev/null || { echo "missing: kubectl" >&2; exit 1; }

for script in kserve-standard-mode-full-install-helm.sh llmisvc-full-install-helm.sh; do
  log "Fetching ${script} (${KSERVE_VERSION})..."
  curl -fsSL -o "$TMP/$script" "$BASE/$script"
  log "Running ${script}..."
  bash "$TMP/$script"
done

log "Gateways:"
kubectl get gateway -A
log "DONE. Deploy the model with: helm upgrade --install model-llmd charts/model-llmd"
