variable "project_id" {
  description = "Nebius project ID, same as in ../base."
  type        = string
}

variable "nebius_profile" {
  type    = string
  default = "default"
}

variable "nebius_iam_token" {
  type      = string
  default   = null
  sensitive = true
}

variable "name" {
  type    = string
  default = "ocr-lab"
}

variable "platform" {
  type    = string
  default = "gpu-l40s-a"
}

variable "preset" {
  description = "gpu-l40s-a presets: 1gpu-8vcpu-32gb, 1gpu-16vcpu-64gb, 1gpu-24vcpu-96gb, 1gpu-32vcpu-128gb, 1gpu-40vcpu-160gb."
  type        = string
  default     = "1gpu-16vcpu-64gb"
}

variable "preemptible" {
  description = "Spot-priced VM that Nebius may stop at any time (60 s SIGTERM). Changing this replaces the VM."
  type        = bool
  default     = true
}

variable "image_family" {
  description = "ubuntu24.04-cuda13.0 ships NVIDIA driver 580, which vLLM v0.31 (CUDA 13) needs."
  type        = string
  default     = "ubuntu24.04-cuda13.0"
}

variable "boot_disk_gib" {
  description = "Holds K3s, the vLLM/llm-d images (~15 GB) and the model weights (~14 GB)."
  type        = number
  default     = 200
}

variable "repo_url" {
  description = "Cloned on the VM by cloud-init. Must be readable without credentials."
  type        = string
  default     = "https://github.com/jeffincloud/ocr-lab.git"
}

variable "repo_ref" {
  type    = string
  default = "claude/project-thread-pwbit0"
}

variable "api_image" {
  description = "When set together with frontend_image, cloud-init also runs scripts/lab-up.sh PROFILE=gpu (platform, observability, model, apps). Empty stops after K3s + GPU runtime."
  type        = string
  default     = ""
}

variable "frontend_image" {
  type    = string
  default = ""
}
