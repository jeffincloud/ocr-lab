output "private_ip" {
  value = local.private_ip
}

output "state" {
  value = nebius_compute_v1_instance.gpu.status.state
}

output "instance_id" {
  value = nebius_compute_v1_instance.gpu.id
}

output "next_steps" {
  value = <<-EOT
    Tunnel up, then:
      ssh -F ${local.base.secrets_dir}/ssh_config ocr-gpu 'sudo journalctl -fu ocr-lab-bootstrap'
      ../lab.sh kubeconfig
  EOT
}
