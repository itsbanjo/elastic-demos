terraform {
  required_version = ">= 1.2.7"

  required_providers {
    ec = {
      source  = "elastic/ec"
      version = "~> 0.11"  # pin to latest minor
    }
  }
}

# Provider reads EC_API_KEY from environment automatically
provider "ec" {}
