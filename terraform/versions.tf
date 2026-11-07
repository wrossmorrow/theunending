terraform {
  required_version = ">= 1.6"

  backend "s3" {
    bucket         = "theunending-ai-raw-content-use1"
    key            = "terraform/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    use_lockfile   = true 
  }

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.0"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = merge({ Project = var.name, ManagedBy = "terraform" }, var.tags)
  }
}
