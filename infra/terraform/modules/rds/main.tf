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
variable "deletion_protection" { type = bool }
variable "backup_retention_period" {
  type    = number
  default = 1
}

resource "random_password" "master" {
  length  = 24
  special = false
}

resource "random_password" "app" {
  length  = 24
  special = false
}

resource "aws_security_group" "db" {
  name   = "${var.name}-rds"
  vpc_id = var.vpc_id
  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = var.client_security_group_ids
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_subnet_group" "this" {
  name       = "${var.name}-rds"
  subnet_ids = var.subnet_ids
}

resource "aws_db_instance" "this" {
  identifier                   = var.name
  engine                       = "postgres"
  engine_version               = "16"
  instance_class               = "db.t4g.micro"
  allocated_storage            = 20
  storage_type                 = "gp3"
  storage_encrypted            = true
  db_name                      = "merchantos"
  username                     = "merchantos"
  password                     = random_password.master.result
  db_subnet_group_name         = aws_db_subnet_group.this.name
  vpc_security_group_ids       = [aws_security_group.db.id]
  publicly_accessible          = false
  multi_az                     = false
  backup_retention_period      = var.backup_retention_period
  backup_window                = "07:00-08:00"
  maintenance_window           = "sun:08:00-sun:09:00"
  deletion_protection          = var.deletion_protection
  skip_final_snapshot          = !var.deletion_protection
  final_snapshot_identifier    = var.deletion_protection ? "${var.name}-final" : null
  auto_minor_version_upgrade   = true
  performance_insights_enabled = false
  apply_immediately            = true
}

output "address" { value = aws_db_instance.this.address }
output "master_username" { value = aws_db_instance.this.username }
output "master_password" {
  value     = random_password.master.result
  sensitive = true
}
output "app_password" {
  value     = random_password.app.result
  sensitive = true
}
output "security_group_id" { value = aws_security_group.db.id }
output "master_url" {
  value     = "postgresql://${aws_db_instance.this.username}:${random_password.master.result}@${aws_db_instance.this.address}:5432/merchantos?sslmode=require"
  sensitive = true
}
output "app_url" {
  value     = "postgresql://merchantos_app:${random_password.app.result}@${aws_db_instance.this.address}:5432/merchantos?sslmode=require"
  sensitive = true
}
