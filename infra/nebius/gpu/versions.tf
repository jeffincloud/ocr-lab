terraform {
  required_version = ">= 1.6"

  required_providers {
    nebius = {
      source  = "nebius/nebius"
      version = ">= 0.6.8"
    }
    local = {
      source  = "hashicorp/local"
      version = ">= 2.4"
    }
  }
}

provider "nebius" {
  parent_id = var.project_id
  token     = var.nebius_iam_token
  profile   = var.nebius_iam_token == null ? { name = var.nebius_profile } : null
}
