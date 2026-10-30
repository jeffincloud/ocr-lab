#!/usr/bin/env bash
# Runs once on a fresh GPU VM (started by cloud-init as the ocr-lab-bootstrap
# systemd unit). Clones the repo, installs K3s + the NVIDIA container runtime
# with scripts/bootstrap.sh, and, when images are configured, the whole lab
# with scripts/lab-up.sh PROFILE=gpu.
#
#   sudo journalctl -fu ocr-lab-bootstrap      # follow progress
set -euo pipefail
source /etc/ocr-lab/env

STATE=/var/lib/ocr-lab
REPO=/opt/ocr-lab
mkdir -p "$STATE"
log() { echo "[ocr-lab-bootstrap] $*"; }

nvidia-smi || { log "no NVIDIA driver on this image; pick a *-cuda13.0 image family"; exit 1; }

if [[ ! -d "$REPO/.git" ]]; then
  log "Cloning ${REPO_URL}@${REPO_REF}"
  git clone --branch "$REPO_REF" "$REPO_URL" "$REPO"
fi

# The API server certificate and the exported kubeconfig use the private IP,
# which is what the WireGuard tunnel reaches.
PRIVATE_IP=$(ip -4 route get 1.1.1.1 | awk '{for (i = 1; i < NF; i++) if ($i == "src") { print $(i + 1); exit }}')

if [[ ! -f "$STATE/k3s.done" ]]; then
  log "K3s + nvidia-container-toolkit (private IP ${PRIVATE_IP})"
  PUBLIC_IP="$PRIVATE_IP" bash "$REPO/scripts/bootstrap.sh"
  touch "$STATE/k3s.done"
fi

install -d -o "$SSH_USER" -g "$SSH_USER" -m 0700 "/home/${SSH_USER}/.kube"
install -o "$SSH_USER" -g "$SSH_USER" -m 0600 /root/kubeconfig-external.yaml "/home/${SSH_USER}/.kube/config"

if ! command -v helm >/dev/null; then
  log "Installing helm"
  curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
fi

if [[ -z "${API_IMAGE}" || -z "${FRONTEND_IMAGE}" ]]; then
  log "API_IMAGE/FRONTEND_IMAGE not set: K3s is ready, skipping lab-up.sh."
  log "Run it later from your laptop: VM_IP=${PRIVATE_IP} SSH_USER=${SSH_USER} SKIP_BOOTSTRAP=1 ./scripts/provision.sh"
  exit 0
fi

if [[ ! -f "$STATE/lab-up.done" ]]; then
  log "scripts/lab-up.sh PROFILE=gpu"
  cd "$REPO"
  KUBECONFIG=/etc/rancher/k3s/k3s.yaml PROFILE=gpu \
    API_IMAGE="$API_IMAGE" FRONTEND_IMAGE="$FRONTEND_IMAGE" ./scripts/lab-up.sh
  touch "$STATE/lab-up.done"
fi
log "Done."
