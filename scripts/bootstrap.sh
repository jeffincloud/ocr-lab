#!/usr/bin/env bash
# TensorDock K3s bootstrap — run as root on a freshly-provisioned
# Ubuntu 22.04 VM with the RTX 4090 + NVIDIA 570 (Open) image.
#
# - Installs nvidia-container-toolkit (K3s auto-detects nvidia runtime
#   when the toolkit is installed BEFORE K3s)
# - Installs K3s with --tls-san=$PUBLIC_IP so the kubeconfig is usable
#   from your laptop without skip-tls-verify
# - Produces /root/kubeconfig-external.yaml with the public IP baked in
#
# Usage:
#   sudo su -
#   ./bootstrap.sh
# or
#   PUBLIC_IP=<your-vm-ip> ./bootstrap.sh   # override auto-detect

set -euxo pipefail

# Traefik off by default: Envoy Gateway (installed by install-llmisvc.sh)
# takes ports 80/443 and serves both the app and the model (Gateway API).
# K3S_EXTRA_ARGS="" keeps Traefik for the original Ingress setup.
K3S_EXTRA_ARGS="${K3S_EXTRA_ARGS---disable=traefik}"

# 1. Resolve public IP
PUBLIC_IP="${PUBLIC_IP:-$(curl -fsS https://api.ipify.org)}"
echo "Using PUBLIC_IP=$PUBLIC_IP"

# 2. NVIDIA driver — defensive check. With the Ubuntu 22.04 + NVIDIA 570
#    (Open) image, this block no-ops because nvidia-smi is preinstalled.
if ! command -v nvidia-smi >/dev/null 2>&1; then
  DEBIAN_FRONTEND=noninteractive apt-get install -y ubuntu-drivers-common
  ubuntu-drivers install --gpgpu
fi

# 3. nvidia-container-toolkit (must be installed BEFORE K3s). GPU images such as
#    Nebius's ubuntu24.04-cuda13.0 ship a version newer than NVIDIA's stable repo,
#    where installing from that repo would be a refused downgrade.
if ! command -v nvidia-ctk >/dev/null 2>&1; then
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | gpg --batch --yes --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -sL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
    | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
    > /etc/apt/sources.list.d/nvidia-container-toolkit.list
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y nvidia-container-toolkit
fi

# Model weights (charts/model-llmd weights.hostPath), writable by the download
# container's UID. On Nebius a persistent disk is already mounted here.
install -d -o 1000 -g 1000 /var/lib/ocr-lab-models

# 4. Pin the kernel. The TensorDock NVIDIA-570 image ships the driver via
#    a .run installer (modules in /lib/modules/$(uname -r)/kernel/drivers/video/),
#    NOT DKMS — so an unattended-upgrade kernel bump leaves the host without
#    nvidia.ko on next boot. Hold the kernel packages until we wire DKMS in.
KERNEL_NOW=$(uname -r)
apt-mark hold linux-image-generic linux-headers-generic linux-generic \
  "linux-image-${KERNEL_NOW}" "linux-headers-${KERNEL_NOW}" \
  "linux-modules-${KERNEL_NOW}" "linux-modules-extra-${KERNEL_NOW}" 2>/dev/null || true

# 5. K3s
curl -sfL https://get.k3s.io \
  | INSTALL_K3S_EXEC="server --write-kubeconfig-mode=644 --tls-san=${PUBLIC_IP} ${K3S_EXTRA_ARGS}" sh -

# 6. Wait for Ready
echo "Waiting for K3s node to be Ready..."
until kubectl get nodes 2>/dev/null | grep -q ' Ready'; do sleep 3; done

# 7. External kubeconfig with public IP baked in
sed "s/127.0.0.1/${PUBLIC_IP}/" /etc/rancher/k3s/k3s.yaml > /root/kubeconfig-external.yaml
chmod 600 /root/kubeconfig-external.yaml

echo
echo "=== DONE ==="
kubectl get nodes -o wide
echo
echo "nvidia runtime registered in K3s containerd:"
grep -A2 'nvidia' /var/lib/rancher/k3s/agent/etc/containerd/config.toml 2>/dev/null \
  || echo "(nvidia runtime not yet registered — next step is the NVIDIA Device Plugin DaemonSet)"
