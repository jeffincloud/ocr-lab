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
#   KUBECONFIG=~/.kube/ocr-lab.config ./scripts/install-llmisvc.sh
set -euo pipefail

KSERVE_VERSION="${KSERVE_VERSION:-v0.21.0}"
BASE="https://raw.githubusercontent.com/kserve/kserve/${KSERVE_VERSION}/hack/setup/quick-install"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

log() { echo "[install-llmisvc] $*"; }
command -v kubectl >/dev/null || { echo "missing: kubectl" >&2; exit 1; }

# KServe v0.21.0's generated quick-install scripts call this function and pass
# GIE_CRDS, but the generator leaves both out (they live in the part of
# hack/setup/infra/manage.kserve-helm.sh it doesn't copy), so the llmisvc install
# dies with "command not found". Exported so the child scripts inherit it. It marks
# the InferencePool CRDs installed earlier as owned by the chart that bundles them.
adopt_existing_crds_for_release() {
  local crd
  for crd in inferencemodelrewrites.llm-d.ai inferenceobjectives.llm-d.ai \
    inferencepools.inference.networking.k8s.io inferencepools.inference.networking.x-k8s.io; do
    if kubectl get crd "$crd" >/dev/null 2>&1; then
      kubectl label crd "$crd" app.kubernetes.io/managed-by=Helm --overwrite
      kubectl annotate crd "$crd" "meta.helm.sh/release-name=$1" "meta.helm.sh/release-namespace=$2" --overwrite
    fi
  done
}
export -f adopt_existing_crds_for_release

for script in kserve-standard-mode-full-install-helm.sh llmisvc-full-install-helm.sh; do
  log "Fetching ${script} (${KSERVE_VERSION})..."
  curl -fsSL -o "$TMP/$script" "$BASE/$script"
  log "Running ${script}..."
  bash "$TMP/$script"
done

log "Gateways:"
kubectl get gateway -A
log "DONE. Deploy the model with: helm upgrade --install model-llmd charts/model-llmd"
