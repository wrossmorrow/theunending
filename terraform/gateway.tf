# ------------------------------------------------------------------------------
# 1. Network Load Balancer (Public Subnets)
# ------------------------------------------------------------------------------
resource "aws_lb" "nlb" {
  name               = "theunending-admin"
  internal           = false
  load_balancer_type = "network"
  subnets            = [
    "subnet-048d51f74f9c3ce05"
  ] # Pass at least 1 public subnet (in the same AZ as your EC2)
  security_groups    = [
    aws_security_group.nlb.id
  ]

  # Recommended if your NLB spans multiple AZs but you only have 1 EC2 instance
  enable_cross_zone_load_balancing = true

  tags = {
    Name = "theunending-admin"
  }
}

# ------------------------------------------------------------------------------
# 2. Target Group (Forwards plain TCP/HTTP on port 8080 to EC2)
# ------------------------------------------------------------------------------
resource "aws_lb_target_group" "admin" {
  name        = "theunending-admin"
  port        = 8080
  protocol    = "TCP"
  vpc_id      = local.vpc_id
  target_type = "instance"

  # Set to false so the EC2 security group only needs to allow aws_security_group.nlb.id
  preserve_client_ip = false

  # Quickly drain connections when redeploying containers (default is 300s)
  deregistration_delay = 30

  health_check {
    enabled             = true
    protocol            = "HTTP" # Change to "TCP" if your app doesn't have an HTTP health route yet
    path                = "/ready" # Omit 'path' and 'matcher' if using protocol = "TCP"
    port                = "9901"
    healthy_threshold   = 3
    unhealthy_threshold = 3
    interval            = 10
    matcher             = "200-399"
  }

  tags = {
    Name = "theunending-admin"
  }
}

# ------------------------------------------------------------------------------
# 3. Register Your Private EC2 Instance with the Target Group
# ------------------------------------------------------------------------------
resource "aws_lb_target_group_attachment" "admin" {
  target_group_arn = aws_lb_target_group.admin.arn
  target_id        = aws_instance.admin.id
  port             = 8080
}

# ------------------------------------------------------------------------------
# 4. TLS 443 Listener (Terminates TLS using your ACM Cert)
# ------------------------------------------------------------------------------
resource "aws_lb_listener" "tls" {
  load_balancer_arn = aws_lb.nlb.arn
  port              = 443
  protocol          = "TLS"
  certificate_arn   = "arn:aws:acm:us-east-1:396610714890:certificate/312f292d-e21b-4c0b-8c43-328ef777f0b0"

  # Modern TLS 1.3 + 1.2 security policy (avoids Terraform's legacy 2016 default)
  ssl_policy = "ELBSecurityPolicy-TLS13-1-2-2021-06"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.admin.arn
  }
}

resource "aws_route53_record" "app" {
  zone_id = "Z0852242JGR4C2WJKAL9"
  name    = "admin.theunending.ai"
  type    = "A"

  alias {
    name                   = aws_lb.nlb.dns_name
    zone_id                = aws_lb.nlb.zone_id
    evaluate_target_health = true
  }
}
