#!/usr/bin/env bash
# Install the cluster-side dependencies the OCR lab needs:
#   1. NVIDIA Device Plugin DaemonSet (advertises nvidia.com/gpu)
#   2. cert-manager (KServe webhooks need it)
#   3. KServe CRDs + KServe in RawDeployment mode
#
# Idempotent: re-running upgrades in place. Run from anywhere with
# KUBECONFIG pointing at the target cluster.
#
# Usage:
#   KUBECONFIG=~/.kube/ocr-lab.config ./scripts/install-cluster-deps.sh

set -euo pipefail

KSERVE_VERSION="${KSERVE_VERSION:-v0.14.0}"
CERT_MANAGER_VERSION="${CERT_MANAGER_VERSION:-v1.16.2}"
DEVICE_PLUGIN_VERSION="${DEVICE_PLUGIN_VERSION:-v0.16.2}"

log() { echo "[install-cluster-deps] $*"; }

require() { command -v "$1" >/dev/null 2>&1 || { echo "missing: $1" >&2; exit 1; }; }
require kubectl
require helm

log "Target cluster:"
kubectl get nodes -o wide

# 1. NVIDIA Device Plugin -----------------------------------------------------
log "Installing NVIDIA Device Plugin ${DEVICE_PLUGIN_VERSION}..."
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: nvidia-device-plugin-daemonset
  namespace: kube-system
spec:
  selector:
    matchLabels:
      name: nvidia-device-plugin-ds
  updateStrategy:
    type: RollingUpdate
  template:
    metadata:
      labels:
        name: nvidia-device-plugin-ds
    spec:
      runtimeClassName: nvidia
      tolerations:
        - key: nvidia.com/gpu
          operator: Exists
          effect: NoSchedule
      priorityClassName: system-node-critical
      containers:
        - name: nvidia-device-plugin-ctr
          image: nvcr.io/nvidia/k8s-device-plugin:${DEVICE_PLUGIN_VERSION}
          env:
            - name: FAIL_ON_INIT_ERROR
              value: "false"
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: ["ALL"]
          volumeMounts:
            - name: device-plugin
              mountPath: /var/lib/kubelet/device-plugins
      volumes:
        - name: device-plugin
          hostPath:
            path: /var/lib/kubelet/device-plugins
EOF

log "Waiting for nvidia.com/gpu to be advertised..."
for i in $(seq 1 60); do
  if kubectl get node -o jsonpath='{.items[*].status.allocatable.nvidia\.com/gpu}' 2>/dev/null | grep -q '^[1-9]'; then
    break
  fi
  sleep 3
done
kubectl get node -o jsonpath='{.items[0].status.allocatable}' | python3 -m json.tool || true

# 2. cert-manager -------------------------------------------------------------
log "Installing cert-manager ${CERT_MANAGER_VERSION}..."
helm repo add jetstack https://charts.jetstack.io >/dev/null 2>&1 || true
helm repo update jetstack >/dev/null
helm upgrade --install cert-manager jetstack/cert-manager \
  --namespace cert-manager --create-namespace \
  --version "${CERT_MANAGER_VERSION}" \
  --set crds.enabled=true \
  --wait --timeout 5m

# 3. KServe -------------------------------------------------------------------
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

log "Downloading KServe ${KSERVE_VERSION} chart artifacts..."
curl -fsSL -o "$TMP/kserve-crd.tgz" \
  "https://github.com/kserve/kserve/releases/download/${KSERVE_VERSION}/helm-chart-kserve-crd-${KSERVE_VERSION}.tgz"
curl -fsSL -o "$TMP/kserve.tgz" \
  "https://github.com/kserve/kserve/releases/download/${KSERVE_VERSION}/helm-chart-kserve-${KSERVE_VERSION}.tgz"

log "Installing kserve-crd..."
helm upgrade --install kserve-crd "$TMP/kserve-crd.tgz" \
  --namespace kserve --create-namespace \
  --wait --timeout 5m

log "Installing kserve (RawDeployment mode)..."
# First install may racy-fail because the chart ships a ModelMesh webhook that
# points at a service that doesn't exist until the controller is Running.
# `--wait` would hang on that. We install without --wait, then apply the fix.
helm upgrade --install kserve "$TMP/kserve.tgz" \
  --namespace kserve \
  --set kserve.controller.deploymentMode=RawDeployment \
  --timeout 10m || true

log "Applying modelmesh-webhook fix (delete-and-reupgrade)..."
# This validates webhook points at a missing service on first install. Removing
# it lets cainjector re-issue the caBundle cleanly on the next upgrade.
kubectl delete validatingwebhookconfiguration \
  modelmesh-servingruntime.serving.kserve.io --ignore-not-found

helm upgrade kserve "$TMP/kserve.tgz" \
  --namespace kserve \
  --reuse-values \
  --wait --timeout 10m

log "Waiting for kserve-controller-manager Ready..."
kubectl wait --for=condition=available deployment/kserve-controller-manager \
  -n kserve --timeout=5m

log "DONE. Cluster is ready for the OCR lab Helm charts."
kubectl get pods -n kserve
