# Optional module. AWS production does not deploy ElastiCache (ADR 0025).
# Keep for a future high-traffic env that actually needs shared rate limits.

terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.80"
    }
    random = {
      source  = "hashicorp/random"
      version = ">= 3.6"
    }
  }
}

variable "name" { type = string }
variable "vpc_id" { type = string }
variable "subnet_ids" { type = list(string) }
variable "client_security_group_ids" { type = list(string) }

resource "random_password" "auth" {
  length  = 32
  special = false
}

resource "aws_security_group" "redis" {
  name   = "${var.name}-redis"
  vpc_id = var.vpc_id
  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = var.client_security_group_ids
  }
}

resource "aws_elasticache_subnet_group" "this" {
  name       = "${var.name}-redis"
  subnet_ids = var.subnet_ids
}

resource "aws_elasticache_replication_group" "this" {
  replication_group_id       = substr(var.name, 0, 20)
  description                = "MerchantOS Redis"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = "cache.t4g.micro"
  num_cache_clusters         = 1
  port                       = 6379
  subnet_group_name          = aws_elasticache_subnet_group.this.name
  security_group_ids         = [aws_security_group.redis.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = random_password.auth.result
  automatic_failover_enabled = false
  multi_az_enabled           = false
}

output "url" {
  value     = "rediss://:${random_password.auth.result}@${aws_elasticache_replication_group.this.primary_endpoint_address}:6379/0"
  sensitive = true
}
output "security_group_id" { value = aws_security_group.redis.id }
