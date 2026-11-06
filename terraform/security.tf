
# NLB security group
resource "aws_security_group" "nlb" {
  name        = "theunending-nlb"
  description = "Controls traffic for the TLS-terminating NLB"
  vpc_id      = local.vpc_id

  tags = {
    Name = "theunending-nlb"
  }
}

# admin instance security group
resource "aws_security_group" "admin" {
  name        = "theunending-admin"
  description = "Controls traffic for the private EC2 application instance"
  vpc_id      = local.vpc_id

  tags = {
    Name = "theunending-admin"
  }
}

# Allow public TLS (443) inbound to NLB
resource "aws_vpc_security_group_ingress_rule" "nlb_tls_in" {
  security_group_id = aws_security_group.nlb.id
  description       = "Allow public TLS traffic"
  from_port         = 443
  to_port           = 443
  ip_protocol       = "tcp"
  cidr_ipv4         = "0.0.0.0/0"
}

# Allow NLB to forward traffic and health checks to the EC2 SG on port 8080

resource "aws_vpc_security_group_egress_rule" "nlb_to_ec2_out_traffic" {
  security_group_id            = aws_security_group.nlb.id
  description                  = "Forward terminated TCP traffic to EC2 app"
  from_port                    = 8080
  to_port                      = 8080
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.admin.id
}

resource "aws_vpc_security_group_egress_rule" "nlb_to_ec2_out_health" {
  security_group_id            = aws_security_group.nlb.id
  description                  = "Forward terminated TCP traffic to EC2 app"
  from_port                    = 9901
  to_port                      = 9901
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.admin.id
}

# Allow inbound traffic from the NLB SG on port 8080 and 9901

resource "aws_vpc_security_group_ingress_rule" "ec2_from_nlb_in_traffic" {
  security_group_id            = aws_security_group.admin.id
  description                  = "Allow app traffic and health checks from NLB"
  from_port                    = 8080
  to_port                      = 8080
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.nlb.id
}

resource "aws_vpc_security_group_ingress_rule" "ec2_from_nlb_in_health" {
  security_group_id            = aws_security_group.admin.id
  description                  = "Allow app traffic and health checks from NLB"
  from_port                    = 9901
  to_port                      = 9901
  ip_protocol                  = "tcp"
  referenced_security_group_id = aws_security_group.nlb.id
}

# Allow outbound HTTPS (443) for ECR pulls, S3 access, and SSM Session Manager
resource "aws_vpc_security_group_egress_rule" "ec2_all_out" {
  security_group_id = aws_security_group.admin.id
  description       = "Allow all outbound traffic (APT HTTP/80, HTTPS/443, etc.)"
  ip_protocol       = "-1" # Equivalent to all protocols and all ports
  cidr_ipv4         = "0.0.0.0/0"
}

# 
# publish task
# 

resource "aws_security_group" "publish" {
  name        = "theunending-publish"
  description = "Publish task: no inbound, HTTPS out (S3/ECR endpoints, admin API callback via NAT)"
  vpc_id      = local.vpc_id

  tags = {
    Name = "theunending-publish"
  }
}

resource "aws_vpc_security_group_egress_rule" "https" {
  security_group_id = aws_security_group.publish.id
  description       = "HTTPS anywhere"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}
