# Nebius: preemptible L40S behind WireGuard

Two Terraform stacks so the expensive part can be thrown away:

| Stack | What | Lifetime |
|---|---|---|
| `base/` | Network + subnet, security group, reserved public IP, model weights disk (93 GiB), SSH key and WireGuard keys. No VM. | Keep it up |
| `gpu/`  | One preemptible `gpu-l40s-a` VM (`1gpu-16vcpu-64gb`, `ubuntu24.04-cuda13.0` = driver 580) bootstrapped by cloud-init. Runs the WireGuard server. | Destroy and rebuild at will |

```
 laptop ──WireGuard (UDP 51820)──▶ GPU VM (reserved public IP, tunnel IP 10.66.0.1)
                                    SG: WireGuard is the only open port
                                    SSH, Kubernetes API and apps: tunnel only
```

The WireGuard server runs on the GPU VM because `eu-north1` projects can have a
non-GPU vCPU quota of 0, which rules out a separate jump server. The tunnel is
only up while the VM runs; the endpoint, keys and client configs survive stops
and rebuilds.

The GPU VM boots, brings up the tunnel, clones this repo, runs
`scripts/bootstrap.sh` (K3s + NVIDIA container toolkit) and, if `api_image` and
`frontend_image` are set, also `scripts/lab-up.sh PROFILE=gpu` (KServe + llm-d,
observability, Qwen3.5, apps).
Progress: `./lab.sh ssh sudo journalctl -fu ocr-lab-bootstrap`.

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
./lab.sh ssh                                 # over the tunnel
./lab.sh kubeconfig && export KUBECONFIG=~/.kube/ocr-lab.config

./lab.sh gpu-down                            # stop paying for the GPU; base stays
./lab.sh gpu-up                              # fresh VM, same public IP, keys and client configs
```

If the images are not set, finish from the laptop over the tunnel:
`VM_IP=$(terraform -chdir=gpu output -raw tunnel_ip) SSH_USER=lab SKIP_BOOTSTRAP=1 ../../scripts/provision.sh`
(`ssh-add .secrets/id_ed25519` first).

## Exposing the app

SSH, the Kubernetes API and everything else stay on the tunnel. To test with real
internet traffic, set `public_app_cidrs = ["0.0.0.0/0"]` in `base/terraform.tfvars`
and run `./lab.sh base`; the app is then at `http://<public_ip>/`. Remove it and
re-run to close the port. It takes effect without restarting the VM.

Traffic is plain HTTP and the upload form has no login, so anyone can use the GPU
and uploads travel unencrypted: use specimen images only. The model's own route on
the same port requires an API key (`charts/model-llmd` `modelAuth`).

## Model weights

The weights live on a separate disk in `base/`, mounted at `/var/lib/ocr-lab-models`.
`./lab.sh gpu-down` leaves it behind, so the next VM skips the 14 GB download;
`./lab.sh down` deletes it. Other images and cluster state are on the boot disk and
do not survive a rebuild.

It is non-replicated: a hardware failure can lose it, which only costs a new
download. Network SSD speed depends on size, and a slow disk shows up as slow model
loading after every preemption, so check `Loading weights took` in the vLLM log.

## Preemption

Nebius may stop the VM at any time (`SIGTERM`, 60 s later `SIGKILL`). It is
**stopped, not deleted**: the disk and the reserved public IP survive. `./lab.sh
start` brings it back; WireGuard, K3s and the lab come up from disk. `./lab.sh
status` shows the state.
`preemptible = false` in `gpu/terraform.tfvars` gives an on-demand VM instead
(changing it replaces the VM).

## Secrets

Terraform generates an ED25519 SSH key and WireGuard keys and writes them to
`infra/nebius/.secrets/` (`id_ed25519`, `wg-<peer>.conf`, `ssh_config`). That
folder, `terraform.tfstate` (which also holds the keys) and `terraform.tfvars`
are gitignored. Nothing secret is committed. Keep the state local or move it to
an encrypted backend before sharing. The WireGuard server key is also in the VM's
cloud-init user data, readable by anyone with access to the Nebius project.

Adding a `wireguard_peers` entry changes the GPU VM's cloud-init, so re-apply both
stacks. Nebius only accepts a cloud-init change on a stopped VM (`./lab.sh stop`
first), and cloud-init doesn't run again on an existing VM, so apply such changes
by hand or rebuild with `./lab.sh gpu-down && ./lab.sh gpu-up`. The public IP is a
reserved allocation, so existing client configs keep working.
