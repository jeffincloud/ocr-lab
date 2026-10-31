# Read by ../gpu through terraform_remote_state.
output "subnet_id" {
  value = nebius_vpc_v1_subnet.lab.id
}

output "gpu_security_group_id" {
  value = nebius_vpc_v1_security_group.gpu.id
}

output "models_disk_id" {
  value = nebius_compute_v1_disk.models.id
}

output "public_ip_allocation_id" {
  value = nebius_vpc_v1_allocation.gpu.id
}

output "public_ip" {
  value = local.public_ip
}

output "ssh_user" {
  value = var.ssh_user
}

output "ssh_public_key" {
  value = trimspace(tls_private_key.ssh.public_key_openssh)
}

output "secrets_dir" {
  value = local.secrets_dir
}

output "tunnel_ip" {
  value = local.wg_server
}

# What the GPU VM's cloud-init needs to run the WireGuard server.
output "wireguard_server" {
  sensitive = true
  value = {
    address     = "${local.wg_server}/${local.wg_mask}"
    port        = var.wireguard_port
    private_key = wireguard_asymmetric_key.server.private_key
    peers = [
      for name, peer in local.wg_peers : {
        name       = name
        public_key = wireguard_asymmetric_key.peer[name].public_key
        address    = peer.address
      }
    ]
  }
}

output "wireguard_configs" {
  value = { for name, f in local_sensitive_file.wireguard_peer : name => f.filename }
}
