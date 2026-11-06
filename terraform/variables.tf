variable "name" {
  description = "Name prefix for all resources."
  type        = string
  default     = "theunending"
}

variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "vpc_cidr" {
  description = "VPC CIDR. Subnets are carved as /20s out of this /16."
  type        = string
  default     = "10.20.0.0/16"

  validation {
    condition     = can(cidrhost(var.vpc_cidr, 0)) && endswith(var.vpc_cidr, "/16")
    error_message = "vpc_cidr must be a valid /16."
  }
}

variable "az_count" {
  description = "Number of AZs to spread subnets across (an NLB needs at least one public subnet; two is the sensible minimum)."
  type        = number
  default     = 2

  validation {
    condition     = var.az_count >= 1 && var.az_count <= 4
    error_message = "az_count must be between 1 and 4."
  }
}

variable "single_nat_gateway" {
  description = "One shared NAT gateway (cheaper) instead of one per AZ (survives an AZ outage)."
  type        = bool
  default     = true
}

variable "interface_endpoints" {
  description = <<-EOT
    Interface endpoint service suffixes (com.amazonaws.<region>.<suffix>) placed in the private subnets.
    Each costs roughly $7/month per AZ plus data. ECR layer downloads come from S3, which the
    free gateway endpoint covers. Add "ssm", "ssmmessages", "ec2messages" for Session Manager
    without NAT.
  EOT
  type        = list(string)
  default     = ["ecr.api", "ecr.dkr"]
}

variable "tags" {
  description = "Extra tags for every resource."
  type        = map(string)
  default     = {}
}
