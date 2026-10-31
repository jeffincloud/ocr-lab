# Disposable half of the lab: the preemptible L40S VM, which also terminates the
# WireGuard tunnel. `terraform destroy` here removes the VM and its boot disk
# only; network, firewall, public IP and keys stay in ../base, so the next
# `terraform apply` is a clean rebuild behind the same tunnel endpoint.

data "terraform_remote_state" "base" {
  backend = "local"
  config = {
    path = "${path.module}/../base/terraform.tfstate"
  }
}

locals {
  base = data.terraform_remote_state.base.outputs
}

resource "nebius_compute_v1_instance" "gpu" {
  name = "${var.name}-gpu"

  resources = {
    platform = var.platform
    preset   = var.preset
  }

  preemptible     = var.preemptible ? { on_preemption = "STOP" } : null
  recovery_policy = var.preemptible ? "FAIL" : null
  # The API requires a pricing model on preemptible VMs. Nebius bills preemptible
  # L40S at a flat rate rather than a moving spot price.
  follows_spot_price = var.preemptible ? {} : null

  boot_disk = {
    attach_mode = "READ_WRITE"
    managed_disk = {
      name = "${var.name}-gpu-boot"
      spec = {
        type                = "NETWORK_SSD"
        size_gibibytes      = var.boot_disk_gib
        source_image_family = { image_family = var.image_family }
      }
    }
  }

  # Model weights, kept in ../base so they outlive this VM.
  secondary_disks = [{
    attach_mode   = "READ_WRITE"
    device_id     = "ocr-models"
    existing_disk = { id = local.base.models_disk_id }
  }]

  # The reserved public IP from ../base. The security group there admits only
  # WireGuard; everything else is reached through the tunnel.
  network_interfaces = [{
    name              = "eth0"
    subnet_id         = local.base.subnet_id
    ip_address        = {}
    public_ip_address = { allocation_id = local.base.public_ip_allocation_id }
    security_groups   = [{ id = local.base.gpu_security_group_id }]
  }]

  cloud_init_user_data = templatefile("${path.module}/templates/gpu-cloud-init.yaml.tftpl", {
    ssh_user       = local.base.ssh_user
    ssh_public_key = local.base.ssh_public_key
    repo_url       = var.repo_url
    repo_ref       = var.repo_ref
    api_image      = var.api_image
    frontend_image = var.frontend_image
    skip_obs       = var.install_observability ? "" : "1"
    tunnel_ip      = local.base.tunnel_ip
    wg             = local.base.wireguard_server
    bootstrap      = file("${path.module}/templates/ocr-lab-bootstrap.sh")
  })
}
