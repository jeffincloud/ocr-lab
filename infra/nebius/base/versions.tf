terraform {
  required_version = ">= 1.6"

  required_providers {
    nebius = {
      source  = "nebius/nebius"
      version = ">= 0.6.8"
    }
    tls = {
      source  = "hashicorp/tls"
      version = ">= 4.0"
    }
    local = {
      source  = "hashicorp/local"
      version = ">= 2.4"
    }
    wireguard = {
      source  = "OJFord/wireguard"
      version = ">= 0.3"
    }
  }
}

# Auth: the Nebius CLI profile (run `nebius profile create` once), or a
# short-lived token via TF_VAR_nebius_iam_token=$(nebius iam get-access-token).
provider "nebius" {
  parent_id = var.project_id
  token     = var.nebius_iam_token
  profile   = var.nebius_iam_token == null ? { name = var.nebius_profile } : null
}
