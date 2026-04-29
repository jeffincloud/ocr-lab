#!/usr/bin/env bash
# End-to-end provisioning for the OCR lab.
#
# Given a fresh GPU VM (Ubuntu 22.04 + NVIDIA driver), this script:
#
#   1. SSH-bootstraps K3s + nvidia-container-toolkit on the VM
#   2. Pulls the kubeconfig back to the operator's machine
#   3. Installs cluster deps (NVIDIA Device Plugin, cert-manager, KServe)
#   4. Helm-installs the model, api, and frontend charts
#
# Re-runnable. Skips steps that are already done.
#
# Usage:
#   VM_IP=<your-vm-ip> SSH_USER=<ssh-user> ./scripts/provision.sh
#
# Env knobs:
#   VM_IP           required — public IP of the GPU VM
#   SSH_USER        default: user
#   KUBECONFIG_OUT  default: ~/.kube/ocr-lab.config
#   API_IMAGE       default: ghcr.io/REPLACE_ME/ocr-lab-api:0.1.0
#   FRONTEND_IMAGE  default: ghcr.io/REPLACE_ME/ocr-lab-frontend:0.1.0
#   SKIP_BOOTSTRAP  set to skip the remote bootstrap step
#   SKIP_DEPS       set to skip the cluster-deps install
#   SKIP_APPS       set to skip the helm app installs

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VM_IP="${VM_IP:?set VM_IP to the GPU VM public IP}"
SSH_USER="${SSH_USER:-user}"
KUBECONFIG_OUT="${KUBECONFIG_OUT:-$HOME/.kube/ocr-lab.config}"
API_IMAGE="${API_IMAGE:-ghcr.io/REPLACE_ME/ocr-lab-api:0.1.0}"
FRONTEND_IMAGE="${FRONTEND_IMAGE:-ghcr.io/REPLACE_ME/ocr-lab-frontend:0.1.0}"

API_REPO="${API_IMAGE%:*}"
API_TAG="${API_IMAGE##*:}"
FRONTEND_REPO="${FRONTEND_IMAGE%:*}"
FRONTEND_TAG="${FRONTEND_IMAGE##*:}"

log() { echo "[provision] $*"; }
require() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 1; }; }

require ssh
require scp
require kubectl
require helm

ssh_run() { ssh -o StrictHostKeyChecking=accept-new "$SSH_USER@$VM_IP" "$@"; }

# --- 1. Remote bootstrap ----------------------------------------------------
if [[ -z "${SKIP_BOOTSTRAP:-}" ]]; then
  log "Copying bootstrap.sh to ${SSH_USER}@${VM_IP}..."
  scp -o StrictHostKeyChecking=accept-new \
    "$REPO_ROOT/scripts/bootstrap.sh" \
    "$SSH_USER@$VM_IP:/tmp/bootstrap.sh"
  log "Running bootstrap.sh on remote (idempotent if k3s already installed)..."
  ssh_run "sudo bash /tmp/bootstrap.sh"
else
  log "SKIP_BOOTSTRAP set — skipping remote bootstrap."
fi

# --- 2. Fetch kubeconfig ----------------------------------------------------
log "Fetching kubeconfig to ${KUBECONFIG_OUT}..."
mkdir -p "$(dirname "$KUBECONFIG_OUT")"
ssh_run "sudo cat /root/kubeconfig-external.yaml" > "$KUBECONFIG_OUT"
chmod 600 "$KUBECONFIG_OUT"
export KUBECONFIG="$KUBECONFIG_OUT"

log "Cluster reachable as:"
kubectl get nodes -o wide

# --- 3. Cluster deps --------------------------------------------------------
if [[ -z "${SKIP_DEPS:-}" ]]; then
  log "Installing cluster deps (device plugin, cert-manager, KServe)..."
  KUBECONFIG="$KUBECONFIG_OUT" "$REPO_ROOT/scripts/install-cluster-deps.sh"
else
  log "SKIP_DEPS set — skipping cluster deps."
fi

# --- 4. Apps ----------------------------------------------------------------
if [[ -z "${SKIP_APPS:-}" ]]; then
  log "Installing model chart (Qwen3-VL ServingRuntime + InferenceService)..."
  helm upgrade --install ocr-model "$REPO_ROOT/charts/model" \
    --namespace default --create-namespace

  log "Patching predictor Deployment to Recreate strategy (single-GPU rollout fix)..."
  # Wait briefly for KServe to create the deployment, then patch.
  for i in $(seq 1 30); do
    if kubectl get deployment qwen3-vl-4b-predictor -n default >/dev/null 2>&1; then
      kubectl patch deployment qwen3-vl-4b-predictor -n default --type=strategic \
        -p '{"spec":{"strategy":{"type":"Recreate","rollingUpdate":null}}}' || true
      break
    fi
    sleep 2
  done

  log "Installing api chart..."
  helm upgrade --install ocr-api "$REPO_ROOT/charts/api" \
    --namespace default \
    --set image.repository="$API_REPO" \
    --set image.tag="$API_TAG"

  log "Installing frontend chart..."
  helm upgrade --install ocr-frontend "$REPO_ROOT/charts/frontend" \
    --namespace default \
    --set image.repository="$FRONTEND_REPO" \
    --set image.tag="$FRONTEND_TAG"
else
  log "SKIP_APPS set — skipping helm app installs."
fi

log "DONE. Cluster summary:"
kubectl get inferenceservice,deployment,svc,ingress -n default
