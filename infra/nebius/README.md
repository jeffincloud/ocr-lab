# Nebius: preemptible L40S + WireGuard jump server

Two Terraform stacks so the expensive part can be thrown away:

| Stack | What | Lifetime |
|---|---|---|
| `base/` | Network + subnet, security groups, reserved public IP, WireGuard jump server (`cpu-d3` 2 vCPU), SSH key and WireGuard keys | Keep it up |
| `gpu/`  | One preemptible `gpu-l40s-a` VM (`1gpu-16vcpu-64gb`, `ubuntu24.04-cuda13.0` = driver 580) bootstrapped by cloud-init | Destroy and rebuild at will |

```
 laptop ──WireGuard (UDP 51820)──▶ jump (only public entry point) ──▶ GPU VM (private IP)
                                    masquerades tunnel traffic          SG: ingress from jump SG only
                                                                        public IP for egress only
```

The GPU VM boots, clones this repo, runs `scripts/bootstrap.sh` (K3s + NVIDIA
container toolkit) and, if `api_image` and `frontend_image` are set, also
`scripts/lab-up.sh PROFILE=gpu` (KServe + llm-d, observability, Qwen3.5, apps).
Progress: `./lab.sh ssh ocr-gpu sudo journalctl -fu ocr-lab-bootstrap`.

## Prerequisites

- Terraform ≥ 1.6, the [Nebius CLI](https://docs.nebius.com/cli) logged in (`nebius profile create`)
- A project in **eu-north1** (the only region with L40S) and GPU quota for `gpu-l40s-a`
- A WireGuard client (app, or `wireguard-tools` for `wg-quick`)

## Use

```bash
cd infra/nebius
cp base/terraform.tfvars.example base/terraform.tfvars   # set project_id, nebius_profile
cp gpu/terraform.tfvars.example  gpu/terraform.tfvars    # same, plus images if you want lab-up

./lab.sh up                                  # base, then GPU VM
sudo wg-quick up "$PWD/.secrets/wg-laptop.conf"   # or import it in the WireGuard app
./lab.sh ssh ocr-gpu                         # over the tunnel
./lab.sh kubeconfig && export KUBECONFIG=~/.kube/ocr-lab.config

./lab.sh gpu-down                            # stop paying for the GPU; base stays
./lab.sh gpu-up                              # fresh VM, same network, keys and tunnel
```

If the images are not set, finish from the laptop over the tunnel:
`VM_IP=$(terraform -chdir=gpu output -raw private_ip) SSH_USER=lab SKIP_BOOTSTRAP=1 ../../scripts/provision.sh`
(`ssh-add .secrets/id_ed25519` first).

## Preemption

Nebius may stop the VM at any time (`SIGTERM`, 60 s later `SIGKILL`). It is
**stopped, not deleted**: the disk survives, the public egress IP changes, the
private IP and the jump server don't. `./lab.sh start` brings it back; K3s and
the lab come up from disk. `./lab.sh status` shows the state.
`preemptible = false` in `gpu/terraform.tfvars` gives an on-demand VM instead
(changing it replaces the VM).

## Secrets

Terraform generates an ED25519 SSH key and WireGuard keys and writes them to
`infra/nebius/.secrets/` (`id_ed25519`, `wg-<peer>.conf`, `ssh_config`). That
folder, `terraform.tfstate` (which also holds the keys) and `terraform.tfvars`
are gitignored. Nothing secret is committed. Keep the state local or move it to
an encrypted backend before sharing.

Adding a `wireguard_peers` entry changes the jump server's cloud-init, which
recreates the jump VM. Its public IP is a reserved allocation, so existing
client configs keep working.
