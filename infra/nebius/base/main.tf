# Persistent half of the lab: network, firewall, SSH + WireGuard keys and the
# jump server. Apply once and leave it up (a 2 vCPU VM). The GPU VM lives in
# ../gpu and can be destroyed and rebuilt without touching anything here.

locals {
  secrets_dir = abspath("${path.module}/../.secrets")
  wg_server   = cidrhost(var.wireguard_cidr, 1)
  wg_mask     = split("/", var.wireguard_cidr)[1]
  wg_peers = {
    for i, peer in var.wireguard_peers : peer => {
      address = cidrhost(var.wireguard_cidr, 10 + i)
    }
  }
  jump_ip   = split("/", nebius_vpc_v1_allocation.jump.status.details.allocated_cidr)[0]
  vpc_cidrs = flatten(nebius_vpc_v1_subnet.lab.status.ipv4_private_pools[*].cidrs)
}

# --- Network -------------------------------------------------------------------
# Own network so the lab's firewall rules don't touch default-network. Private
# and public pools come from the region defaults.
resource "nebius_vpc_v1_network" "lab" {
  name = var.name
}

resource "nebius_vpc_v1_subnet" "lab" {
  name       = var.name
  network_id = nebius_vpc_v1_network.lab.id
}

# --- Firewall ------------------------------------------------------------------
# Security groups deny anything not allowed. The jump server only accepts
# WireGuard from outside; the GPU VM only accepts traffic from the jump server
# (tunnel clients are masqueraded to the jump's private IP).
resource "nebius_vpc_v1_security_group" "jump" {
  name       = "${var.name}-jump"
  network_id = nebius_vpc_v1_network.lab.id
}

resource "nebius_vpc_v1_security_group" "gpu" {
  name       = "${var.name}-gpu"
  network_id = nebius_vpc_v1_network.lab.id
}

resource "nebius_vpc_v1_security_rule" "jump_wireguard" {
  parent_id = nebius_vpc_v1_security_group.jump.id
  name      = "wireguard-in"
  access    = "ALLOW"
  protocol  = "UDP"
  ingress = {
    source_cidrs      = var.wireguard_allowed_cidrs
    destination_ports = [var.wireguard_port]
  }
}

resource "nebius_vpc_v1_security_rule" "jump_ssh_break_glass" {
  count     = length(var.ssh_break_glass_cidrs) > 0 ? 1 : 0
  parent_id = nebius_vpc_v1_security_group.jump.id
  name      = "ssh-break-glass"
  access    = "ALLOW"
  protocol  = "TCP"
  ingress = {
    source_cidrs      = var.ssh_break_glass_cidrs
    destination_ports = [22]
  }
}

resource "nebius_vpc_v1_security_rule" "jump_egress" {
  parent_id = nebius_vpc_v1_security_group.jump.id
  name      = "all-out"
  access    = "ALLOW"
  protocol  = "ANY"
  egress    = {}
}

resource "nebius_vpc_v1_security_rule" "gpu_from_jump" {
  parent_id = nebius_vpc_v1_security_group.gpu.id
  name      = "from-jump"
  access    = "ALLOW"
  protocol  = "ANY"
  ingress = {
    source_security_group_id = nebius_vpc_v1_security_group.jump.id
  }
}

# Model weights, container images, Hugging Face and GitHub all come in over
# the GPU VM's own public IP; nothing can connect in on it.
resource "nebius_vpc_v1_security_rule" "gpu_egress" {
  parent_id = nebius_vpc_v1_security_group.gpu.id
  name      = "all-out"
  access    = "ALLOW"
  protocol  = "ANY"
  egress    = {}
}

# --- Keys ----------------------------------------------------------------------
# Generated here and written to infra/nebius/.secrets/ (gitignored). They are
# also in terraform.tfstate, which stays local and is gitignored too.
resource "tls_private_key" "ssh" {
  algorithm = "ED25519"
}

resource "local_sensitive_file" "ssh_private_key" {
  filename        = "${local.secrets_dir}/id_ed25519"
  content         = tls_private_key.ssh.private_key_openssh
  file_permission = "0600"
}

resource "local_file" "ssh_public_key" {
  filename        = "${local.secrets_dir}/id_ed25519.pub"
  content         = tls_private_key.ssh.public_key_openssh
  file_permission = "0644"
}

resource "wireguard_asymmetric_key" "server" {}

resource "wireguard_asymmetric_key" "peer" {
  for_each = local.wg_peers
}

resource "local_sensitive_file" "wireguard_peer" {
  for_each = local.wg_peers
  filename = "${local.secrets_dir}/wg-${each.key}.conf"
  content = templatefile("${path.module}/templates/wg-client.conf.tftpl", {
    address     = "${each.value.address}/32"
    private_key = wireguard_asymmetric_key.peer[each.key].private_key
    server_key  = wireguard_asymmetric_key.server.public_key
    endpoint    = "${local.jump_ip}:${var.wireguard_port}"
    allowed_ips = join(", ", concat([var.wireguard_cidr], local.vpc_cidrs))
  })
  file_permission = "0600"
}

# --- Jump server ---------------------------------------------------------------
# Reserved public IP, so the WireGuard endpoint survives a jump server rebuild.
resource "nebius_vpc_v1_allocation" "jump" {
  name = "${var.name}-jump"
  ipv4_public = {
    subnet_id = nebius_vpc_v1_subnet.lab.id
  }
}

resource "nebius_compute_v1_instance" "jump" {
  name = "${var.name}-jump"

  resources = {
    platform = var.jump_platform
    preset   = var.jump_preset
  }

  boot_disk = {
    attach_mode = "READ_WRITE"
    managed_disk = {
      name = "${var.name}-jump-boot"
      spec = {
        type                = "NETWORK_SSD"
        size_gibibytes      = 20
        source_image_family = { image_family = var.jump_image_family }
      }
    }
  }

  network_interfaces = [{
    name              = "eth0"
    subnet_id         = nebius_vpc_v1_subnet.lab.id
    ip_address        = {}
    public_ip_address = { allocation_id = nebius_vpc_v1_allocation.jump.id }
    security_groups   = [{ id = nebius_vpc_v1_security_group.jump.id }]
  }]

  cloud_init_user_data = templatefile("${path.module}/templates/jump-cloud-init.yaml.tftpl", {
    ssh_user       = var.ssh_user
    ssh_public_key = trimspace(tls_private_key.ssh.public_key_openssh)
    wg_address     = "${local.wg_server}/${local.wg_mask}"
    wg_cidr        = var.wireguard_cidr
    wg_port        = var.wireguard_port
    wg_private_key = wireguard_asymmetric_key.server.private_key
    wg_peers = [
      for name, peer in local.wg_peers : {
        name       = name
        public_key = wireguard_asymmetric_key.peer[name].public_key
        address    = peer.address
      }
    ]
  })
}

resource "local_file" "ssh_config" {
  filename = "${local.secrets_dir}/ssh_config"
  content  = <<-EOT
    # Generated by infra/nebius/base. Use with: ssh -F ${local.secrets_dir}/ssh_config <host>
    # Reach these hosts with the WireGuard tunnel up (wg-quick up ${local.secrets_dir}/wg-<peer>.conf).
    Host ocr-jump
      HostName ${local.wg_server}
      User ${var.ssh_user}
      IdentityFile ${local.secrets_dir}/id_ed25519
      IdentitiesOnly yes

    Include ${local.secrets_dir}/ssh_config.gpu
  EOT
}
