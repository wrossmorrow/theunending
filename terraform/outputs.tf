output "vpc_id" {
  value = local.vpc_id
}

output "vpc_cidr" {
  value = aws_vpc.this.cidr_block
}

output "azs" {
  value = local.azs
}

output "public_subnet_ids" {
  description = "For the NLB (and NAT)."
  value       = aws_subnet.public[*].id
}

output "private_subnet_ids" {
  description = "For the instance(s)."
  value       = aws_subnet.private[*].id
}

output "nat_public_ips" {
  description = "Egress IPs of the private subnets, e.g. for allowlisting on the far side."
  value       = aws_eip.nat[*].public_ip
}

output "s3_endpoint_id" {
  value = aws_vpc_endpoint.s3.id
}

output "interface_endpoint_ids" {
  value = { for k, v in aws_vpc_endpoint.interface : k => v.id }
}

output "nlb_dns_name" {
  description = "DNS name of the Network Load Balancer"
  value       = aws_lb.nlb.dns_name
}

# 
# Everything the admin API needs to call ecs.run_task.
# 

output "cluster_name" {
  value = aws_ecs_cluster.publish.name
}

output "cluster_arn" {
  value = aws_ecs_cluster.publish.arn
}

output "task_family" {
  description = "Pass this (not a revision ARN) as taskDefinition to get the latest revision."
  value       = aws_ecs_task_definition.publish.family
}

output "task_definition_arn" {
  value = aws_ecs_task_definition.publish.arn
}

output "container_name" {
  description = "Name to use in containerOverrides."
  value       = "publish"
}

output "launcher_policy_arn" {
  description = "Attach to whatever role calls RunTask (if launcher_role_name wasn't set)."
  value       = aws_iam_policy.launcher.arn
}

output "sns_topic_arn" {
  description = "SNS topic for admin run status notifications."
  value       = aws_sns_topic.admin_notifications.arn
}

output "api_env" {
  description = "Drop-in env for the admin API."
  value = {
    PUBLISH_CLUSTER        = aws_ecs_cluster.publish.name
    PUBLISH_TASK_FAMILY    = aws_ecs_task_definition.publish.family
    PUBLISH_CONTAINER      = "publish"
    PUBLISH_SUBNETS        = join(",", local.private_subnet_ids)
    PUBLISH_SECURITY_GROUP = aws_security_group.publish.id
    SNS_TOPIC_ARN          = aws_sns_topic.admin_notifications.arn
  }
}

# 
# For builds
# 

output "github_actions_role_arn" {
  value       = aws_iam_role.github_actions.arn
  description = "Copy this ARN to your GitHub Secrets/Variables AWS_ROLE_ARN"
}

output "github_actions_role_arn_pr" {
  value       = aws_iam_role.github_actions_pr.arn
  description = "Copy this ARN to your GitHub Secrets/Variables PR_AWS_ROLE_ARN"
}
