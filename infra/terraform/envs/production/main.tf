terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.80"
    }
  }
  backend "s3" {
    bucket         = "merchantos-tfstate-guransh-2026"
    key            = "production/terraform.tfstate"
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
      Environment = "production"
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
  name       = "merchantos-prod"
  enable_tls = var.domain_name != ""
  public_url = (
    var.public_base_url != "" ? var.public_base_url :
    local.enable_tls ? "https://${var.domain_name}" :
    "http://replace-with-task-public-ip"
  )
  site_address = local.enable_tls ? var.domain_name : "http://:80"
}

module "network" {
  source = "../../modules/network"
  name   = local.name
  cidr   = "10.50.0.0/16"
  azs    = slice(data.aws_availability_zones.available.names, 0, 2)
}

module "ecr" {
  source = "../../modules/ecr"
  name   = local.name
  repos  = ["api", "worker", "web", "caddy"]
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
  client_security_group_ids = [module.network.edge_security_group_id, module.network.worker_security_group_id]
  deletion_protection       = true
  backup_retention_period   = 1
}

module "secrets" {
  source              = "../../modules/secrets"
  name                = local.name
  master_database_url = module.rds.master_url
  app_database_url    = module.rds.app_url
  app_db_password     = module.rds.app_password
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

module "ecs" {
  source                   = "../../modules/ecs"
  name                     = local.name
  public_subnet_ids        = module.network.public_subnet_ids
  edge_security_group_id   = module.network.edge_security_group_id
  worker_security_group_id = module.network.worker_security_group_id
  execution_role_arn       = module.iam.execution_role_arn
  api_role_arn             = module.iam.api_role_arn
  worker_role_arn          = module.iam.worker_role_arn
  api_image                = "${module.ecr.repository_urls["api"]}:${var.image_tag}"
  worker_image             = "${module.ecr.repository_urls["worker"]}:${var.image_tag}"
  web_image                = "${module.ecr.repository_urls["web"]}:${var.image_tag}"
  caddy_image              = "${module.ecr.repository_urls["caddy"]}:${var.image_tag}"
  secret_arn               = module.secrets.app_secret_arn
  queue_name               = module.sqs.queue_name
  queue_url                = module.sqs.queue_url
  region                   = var.region
  web_origin               = local.public_url
  api_public_base_url      = local.public_url
  shopify_redirect_uri     = "${local.public_url}/api/v1/auth/shopify/callback"
  site_address             = local.site_address
  acme_email               = var.alarm_email
  desired_count            = 1
  enable_services          = var.enable_services
  llm_provider             = var.llm_provider
}

module "observability" {
  source       = "../../modules/observability"
  name         = local.name
  alarm_email  = var.alarm_email
  cluster_name = module.ecs.cluster_name
  queue_name   = module.sqs.queue_name
  dlq_name     = module.sqs.dlq_name
}

output "public_url" { value = local.public_url }
output "ecr_urls" { value = module.ecr.repository_urls }
output "github_role_arn" { value = module.iam.github_role_arn }
output "migrate_task_definition" { value = module.ecs.migrate_task_definition }
output "cluster_name" { value = module.ecs.cluster_name }
output "queue_url" { value = module.sqs.queue_url }
output "public_subnet_ids" { value = module.network.public_subnet_ids }
output "ecs_security_group_id" { value = module.ecs.ecs_security_group_id }
