#!/usr/bin/env bash
# Nebius lab lifecycle. The base stack (network, firewall, keys, WireGuard jump
# server) stays up; the preemptible GPU VM is cheap to throw away and rebuild.
#
#   ./lab.sh up            base + GPU VM (first time)
#   ./lab.sh gpu-up        (re)create the GPU VM only
#   ./lab.sh gpu-down      destroy the GPU VM and its disk; keeps everything else
#   ./lab.sh stop|start    stop or start the GPU VM in place (also: restart after preemption)
#   ./lab.sh status        GPU VM state
#   ./lab.sh ssh [host]    ssh to ocr-gpu (default) or ocr-jump over the tunnel
#   ./lab.sh kubeconfig    copy the K3s kubeconfig to ~/.kube/ocr-lab.config
#   ./lab.sh down          destroy everything
#
# Auth: Nebius CLI profile (nebius_profile in terraform.tfvars), or export
# NEBIUS_IAM_TOKEN=$(nebius iam get-access-token) before running.
# Extra args are passed to terraform (e.g. ./lab.sh gpu-up -auto-approve).
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
SECRETS="$HERE/.secrets"
KUBECONFIG_OUT="${KUBECONFIG_OUT:-$HOME/.kube/ocr-lab.config}"

if [[ -n "${NEBIUS_IAM_TOKEN:-}" ]]; then
  export TF_VAR_nebius_iam_token="$NEBIUS_IAM_TOKEN"
fi

tf() { local dir="$1"; shift; terraform -chdir="$HERE/$dir" "$@"; }
init() { [[ -d "$HERE/$1/.terraform" ]] || tf "$1" init -input=false; }
gpu_id() { tf gpu output -raw instance_id; }

cmd="${1:-help}"; shift || true
case "$cmd" in
  up)
    init base; tf base apply "$@"
    init gpu; tf gpu apply "$@"
    echo; echo "WireGuard client config(s): $SECRETS/wg-*.conf"
    ;;
  base)     init base; tf base apply "$@" ;;
  gpu-up)   init gpu; tf gpu apply "$@" ;;
  gpu-down) init gpu; tf gpu destroy "$@" ;;
  down)
    init gpu; tf gpu destroy "$@"
    init base; tf base destroy "$@"
    ;;
  stop)   nebius compute instance stop --id "$(gpu_id)" ;;
  start)  nebius compute instance start --id "$(gpu_id)" ;;
  status) nebius compute instance get --id "$(gpu_id)" --format jsonpath='{.status.state}'; echo ;;
  ssh)    ssh -F "$SECRETS/ssh_config" "${1:-ocr-gpu}" "${@:2}" ;;
  kubeconfig)
    mkdir -p "$(dirname "$KUBECONFIG_OUT")"
    ssh -F "$SECRETS/ssh_config" ocr-gpu 'cat ~/.kube/config' > "$KUBECONFIG_OUT"
    chmod 600 "$KUBECONFIG_OUT"
    echo "export KUBECONFIG=$KUBECONFIG_OUT"
    ;;
  *) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 1 ;;
esac
