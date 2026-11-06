
# --- VPC & internet gateway -------------------------------------------------

resource "aws_vpc" "this" {
  cidr_block = var.vpc_cidr

  # Both required for interface endpoints' private DNS names to resolve.
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = var.name }
}

resource "aws_internet_gateway" "this" {
  vpc_id = local.vpc_id
  tags   = { Name = var.name }
}

# --- Subnets ----------------------------------------------------------------

resource "aws_subnet" "public" {
  count = var.az_count

  vpc_id            = local.vpc_id
  availability_zone = local.azs[count.index]
  cidr_block        = local.public_cidrs[count.index]

  # Only the NLB and NAT live here; nothing should get a public IP by accident.
  map_public_ip_on_launch = false

  tags = {
    Name                     = "${var.name}-public-${local.azs[count.index]}"
    Tier                     = "public"
    "kubernetes.io/role/elb" = "1" # harmless now; lets EKS/LB controller find these later
  }
}

resource "aws_subnet" "private" {
  count = var.az_count

  vpc_id            = local.vpc_id
  availability_zone = local.azs[count.index]
  cidr_block        = local.private_cidrs[count.index]

  tags = {
    Name                              = "${var.name}-private-${local.azs[count.index]}"
    Tier                              = "private"
    "kubernetes.io/role/internal-elb" = "1"
  }
}

# --- Public routing ---------------------------------------------------------

resource "aws_route_table" "public" {
  vpc_id = local.vpc_id
  tags   = {
    Name = "${var.name}-public"
  }
}

resource "aws_route" "public_internet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

resource "aws_route_table_association" "public" {
  count = var.az_count

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# --- NAT egress for private subnets -----------------------------------------

resource "aws_eip" "nat" {
  count = local.nat_count

  domain = "vpc"
  tags   = { Name = "${var.name}-nat-${local.azs[count.index]}" }

  depends_on = [aws_internet_gateway.this]
}

resource "aws_nat_gateway" "this" {
  count = local.nat_count

  allocation_id = aws_eip.nat[count.index].id
  subnet_id     = aws_subnet.public[count.index].id
  tags          = { Name = "${var.name}-nat-${local.azs[count.index]}" }

  depends_on = [aws_internet_gateway.this]
}

# One route table per private subnet, so switching single_nat_gateway later
# only changes routes, not associations.
resource "aws_route_table" "private" {
  count = var.az_count

  vpc_id = local.vpc_id
  tags   = { Name = "${var.name}-private-${local.azs[count.index]}" }
}

resource "aws_route" "private_nat" {
  count = var.az_count

  route_table_id         = aws_route_table.private[count.index].id
  destination_cidr_block = "0.0.0.0/0"
  nat_gateway_id         = aws_nat_gateway.this[var.single_nat_gateway ? 0 : count.index].id
}

resource "aws_route_table_association" "private" {
  count = var.az_count

  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

# --- S3 gateway endpoint (free) ---------------------------------------------
# Keeps S3 traffic (presigning reads, copies, ECR image layers) off the NAT.

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = local.vpc_id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"

  route_table_ids = concat(aws_route_table.private[*].id, [aws_route_table.public.id])

  tags = { Name = "${var.name}-s3" }
}

# --- Interface endpoints (ECR by default) ------------------------------------

resource "aws_security_group" "endpoints" {
  name        = "${var.name}-vpc-endpoints"
  description = "HTTPS from inside the VPC to interface endpoints"
  vpc_id      = local.vpc_id

  tags = { Name = "${var.name}-vpc-endpoints" }
}

resource "aws_vpc_security_group_ingress_rule" "endpoints_https" {
  security_group_id = aws_security_group.endpoints.id
  description       = "HTTPS from the VPC"
  cidr_ipv4         = aws_vpc.this.cidr_block
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_endpoint" "interface" {
  for_each = toset(var.interface_endpoints)

  vpc_id              = local.vpc_id
  service_name        = "com.amazonaws.${var.region}.${each.key}"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = aws_subnet.private[*].id
  security_group_ids  = [aws_security_group.endpoints.id]
  private_dns_enabled = true

  tags = { Name = "${var.name}-${each.key}" }
}
