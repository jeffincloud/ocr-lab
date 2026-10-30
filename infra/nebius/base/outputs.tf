# Read by ../gpu through terraform_remote_state.
output "subnet_id" {
  value = nebius_vpc_v1_subnet.lab.id
}

output "gpu_security_group_id" {
  value = nebius_vpc_v1_security_group.gpu.id
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

output "jump_public_ip" {
  value = local.jump_ip
}

output "jump_private_ip" {
  value = split("/", nebius_compute_v1_instance.jump.status.network_interfaces[0].ip_address.address)[0]
}

output "vpc_cidrs" {
  value = local.vpc_cidrs
}

output "wireguard_configs" {
  value = { for name, f in local_sensitive_file.wireguard_peer : name => f.filename }
}
