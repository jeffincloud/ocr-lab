variable "project_id" {
  description = "Nebius project ID (project-...). L40S is only offered in eu-north1, so use a project in that region."
  type        = string
}

variable "nebius_profile" {
  description = "Nebius CLI profile used for auth when nebius_iam_token is not set."
  type        = string
  default     = "default"
}

variable "nebius_iam_token" {
  description = "Optional IAM token (nebius iam get-access-token). Overrides the profile."
  type        = string
  default     = null
  sensitive   = true
}

variable "name" {
  description = "Prefix for every resource name."
  type        = string
  default     = "ocr-lab"
}

variable "ssh_user" {
  description = "Login user created on the GPU VM."
  type        = string
  default     = "lab"
}

variable "models_disk_gib" {
  description = "Persistent disk for model weights, in multiples of 93 GiB (non-replicated disks). Qwen3.5-9B FP8 takes 14 GB."
  type        = number
  default     = 93
}

variable "wireguard_port" {
  type    = number
  default = 51820
}

variable "wireguard_cidr" {
  description = "Tunnel network. The GPU VM takes .1, peers take .10 onwards."
  type        = string
  default     = "10.66.0.0/24"
}

variable "wireguard_peers" {
  description = "One client config is generated per name (laptop, a second device, a teammate...)."
  type        = list(string)
  default     = ["laptop"]
}

variable "wireguard_allowed_cidrs" {
  description = "Source CIDRs allowed to reach the WireGuard UDP port. WireGuard ignores unauthenticated packets, so the internet is a sane default; narrow it to your own IP if you can."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "public_app_cidrs" {
  description = "CIDRs allowed to reach the app on port 80 of the public IP, e.g. [\"0.0.0.0/0\"] while testing with real traffic. Plain HTTP, so use specimens only. Empty keeps the app on the tunnel."
  type        = list(string)
  default     = []
}

variable "ssh_break_glass_cidrs" {
  description = "Optional CIDRs (e.g. [\"203.0.113.7/32\"]) allowed to SSH to the GPU VM's public IP if the tunnel is broken. Empty keeps SSH reachable only through WireGuard."
  type        = list(string)
  default     = []
}
