terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.80"
    }
  }
  backend "s3" {
    bucket         = "merchantos-tfstate-replace-me"
    key            = "staging/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "merchantos-tf-lock"
    encrypt        = true
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = {
      Project     = "merchantos"
      Environment = "staging"
    }
  }
}

variable "region" { default = "us-east-1" }
variable "image_tag" { default = "unreleased" }
variable "enable_services" { default = false }
variable "llm_provider" { default = "fake" }
variable "public_base_url" { default = "" }
variable "github_repo" { default = "" }
variable "alarm_email" { default = "" }
variable "domain_name" { default = "" }
variable "shopify_api_key" {
  type      = string
  default   = ""
  sensitive = true
}
variable "shopify_api_secret" {
  type      = string
  default   = ""
  sensitive = true
}
variable "openai_api_key" {
  type      = string
  default   = ""
  sensitive = true
}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name       = "merchantos-staging"
  enable_tls = var.domain_name != ""
  public_url = (
    var.public_base_url != "" ? var.public_base_url :
    local.enable_tls ? "https://${var.domain_name}" :
    "http://replace-with-alb-dns"
  )
}

module "network" {
  source = "../../modules/network"
  name   = local.name
  cidr   = "10.40.0.0/16"
  azs    = slice(data.aws_availability_zones.available.names, 0, 2)
}

module "ecr" {
  source = "../../modules/ecr"
  name   = local.name
  repos  = ["api", "worker", "web"]
}

module "sqs" {
  source = "../../modules/sqs"
  name   = local.name
}

module "rds" {
  source                    = "../../modules/rds"
  name                      = local.name
  vpc_id                    = module.network.vpc_id
  subnet_ids                = module.network.private_subnet_ids
  client_security_group_ids = [module.network.ecs_security_group_id]
  deletion_protection       = false
}

module "redis" {
  source                    = "../../modules/redis"
  name                      = local.name
  vpc_id                    = module.network.vpc_id
  subnet_ids                = module.network.private_subnet_ids
  client_security_group_ids = [module.network.ecs_security_group_id]
}

module "secrets" {
  source              = "../../modules/secrets"
  name                = local.name
  master_database_url = module.rds.master_url
  app_database_url    = module.rds.app_url
  app_db_password     = module.rds.app_password
  redis_url           = module.redis.url
  shopify_api_key     = var.shopify_api_key
  shopify_api_secret  = var.shopify_api_secret
  openai_api_key      = var.openai_api_key
}

module "iam" {
  source         = "../../modules/iam"
  name           = local.name
  region         = var.region
  secret_arns    = [module.secrets.app_secret_arn]
  jobs_queue_arn = module.sqs.queue_arn
  dlq_arn        = module.sqs.dlq_arn
  github_repo    = var.github_repo
}

resource "aws_acm_certificate" "this" {
  count             = local.enable_tls ? 1 : 0
  domain_name       = var.domain_name
  validation_method = "DNS"
}

module "ecs" {
  source                = "../../modules/ecs"
  name                  = local.name
  vpc_id                = module.network.vpc_id
  public_subnet_ids     = module.network.public_subnet_ids
  alb_security_group_id = module.network.alb_security_group_id
  ecs_security_group_id = module.network.ecs_security_group_id
  execution_role_arn    = module.iam.execution_role_arn
  api_role_arn          = module.iam.api_role_arn
  worker_role_arn       = module.iam.worker_role_arn
  api_image             = "${module.ecr.repository_urls["api"]}:${var.image_tag}"
  worker_image          = "${module.ecr.repository_urls["worker"]}:${var.image_tag}"
  web_image             = "${module.ecr.repository_urls["web"]}:${var.image_tag}"
  secret_arn            = module.secrets.app_secret_arn
  queue_name            = module.sqs.queue_name
  queue_url             = module.sqs.queue_url
  region                = var.region
  web_origin            = local.public_url
  api_public_base_url   = local.public_url
  shopify_redirect_uri  = "${local.public_url}/api/v1/auth/shopify/callback"
  enable_https          = local.enable_tls
  certificate_arn       = try(aws_acm_certificate.this[0].arn, "")
  desired_count         = 1
  enable_services       = var.enable_services
  llm_provider          = var.llm_provider
}

module "observability" {
  source                      = "../../modules/observability"
  name                        = local.name
  alarm_email                 = var.alarm_email
  alb_arn_suffix              = module.ecs.alb_arn_suffix
  api_target_group_arn_suffix = module.ecs.api_target_group_arn_suffix
  queue_name                  = module.sqs.queue_name
  dlq_name                    = module.sqs.dlq_name
}

output "alb_dns_name" { value = module.ecs.alb_dns_name }
output "public_url" { value = local.public_url }
output "ecr_urls" { value = module.ecr.repository_urls }
output "github_role_arn" { value = module.iam.github_role_arn }
output "migrate_task_definition" { value = module.ecs.migrate_task_definition }
output "cluster_name" { value = module.ecs.cluster_name }
output "queue_url" { value = module.sqs.queue_url }
output "public_subnet_ids" { value = module.network.public_subnet_ids }
output "ecs_security_group_id" { value = module.network.ecs_security_group_id }
