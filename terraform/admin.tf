
resource "aws_instance" "admin" {
  ami                    = "ami-0d97d7f07b25dd693"
  instance_type          = "c7a.large"
  subnet_id              = "subnet-091afa30f85bb10ed"  # TODO: pull from local.private_dns
  vpc_security_group_ids = [
    aws_security_group.admin.id
  ]

  # Attach the IAM Instance Profile
  iam_instance_profile = aws_iam_instance_profile.theunending_admin.name

  # Best practice: Require IMDSv2 and allow 2 hops so Docker containers can reach metadata
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  user_data = file("${path.module}/userdata.sh")

  tags = {
    Name = "theunending-admin"
  }
}
