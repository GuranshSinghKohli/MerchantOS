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
variable "master_database_url" {
  type      = string
  sensitive = true
}
variable "app_database_url" {
  type      = string
  sensitive = true
}
variable "app_db_password" {
  type      = string
  sensitive = true
}
variable "redis_url" {
  type      = string
  sensitive = true
}
variable "shopify_api_key" {
  type      = string
  sensitive = true
  default   = ""
}
variable "shopify_api_secret" {
  type      = string
  sensitive = true
  default   = ""
}
variable "openai_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

resource "random_id" "token_key" {
  byte_length = 32
}

resource "aws_secretsmanager_secret" "app" {
  name = "${var.name}/app"
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    DATABASE_URL                 = var.app_database_url
    MASTER_DATABASE_URL          = var.master_database_url
    APP_DB_PASSWORD              = var.app_db_password
    REDIS_URL                    = var.redis_url
    TOKEN_ENCRYPTION_KEY         = replace(replace(random_id.token_key.b64_std, "+", "-"), "/", "_")
    SHOPIFY_API_KEY              = var.shopify_api_key
    SHOPIFY_API_SECRET           = var.shopify_api_secret
    OPENAI_API_KEY               = var.openai_api_key
    TOKEN_ENCRYPTION_KEY_VERSION = "aws-v1"
  })
  lifecycle {
    ignore_changes = [secret_string]
  }
}

output "app_secret_arn" { value = aws_secretsmanager_secret.app.arn }
