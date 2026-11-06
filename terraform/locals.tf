
data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

data "aws_availability_zones" "available" {
  state = "available"

  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

locals {
  account   = data.aws_caller_identity.current.account_id
  partition = data.aws_partition.current.partition
  region = data.aws_region.current.name

  azs = slice(data.aws_availability_zones.available.names, 0, var.az_count)

  # /20s: public in the first block (10.20.0.0, 10.20.16.0, ...),
  # private starting at index 8 (10.20.128.0, 10.20.144.0, ...).
  public_cidrs  = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 4, i)]
  private_cidrs = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 4, i + 8)]

  nat_count = var.single_nat_gateway ? 1 : var.az_count

  vpc_id = aws_vpc.this.id
  public_subnet_ids = aws_subnet.public[*].id
  private_subnet_ids = aws_subnet.private[*].id

  image_ref = "${local.account}.dkr.ecr.${local.region}.amazonaws.com/theunending/theunending:${var.publish_image_tag}"
}
