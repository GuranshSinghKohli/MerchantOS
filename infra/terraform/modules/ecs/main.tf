terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.80"
    }
  }
}

variable "name" { type = string }
variable "public_subnet_ids" { type = list(string) }
variable "edge_security_group_id" { type = string }
variable "worker_security_group_id" { type = string }
variable "execution_role_arn" { type = string }
variable "api_role_arn" { type = string }
variable "worker_role_arn" { type = string }
variable "api_image" { type = string }
variable "worker_image" { type = string }
variable "web_image" { type = string }
variable "caddy_image" { type = string }
variable "secret_arn" { type = string }
variable "queue_name" { type = string }
variable "queue_url" { type = string }
variable "region" { type = string }
variable "web_origin" { type = string }
variable "api_public_base_url" { type = string }
variable "shopify_redirect_uri" { type = string }
variable "site_address" { type = string }
variable "desired_count" { type = number }
variable "enable_services" { type = bool }
variable "llm_provider" { type = string }

resource "aws_cloudwatch_log_group" "this" {
  for_each          = toset(["edge", "worker", "migrate"])
  name              = "/merchantos/${var.name}/${each.key}"
  retention_in_days = 7
}

resource "aws_ecs_cluster" "this" {
  name = var.name
  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}

resource "aws_ecs_cluster_capacity_providers" "this" {
  cluster_name       = aws_ecs_cluster.this.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]
  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }
}

locals {
  api_secret_keys = [
    "DATABASE_URL",
    "TOKEN_ENCRYPTION_KEY",
    "TOKEN_ENCRYPTION_KEY_VERSION",
    "SHOPIFY_API_KEY",
    "SHOPIFY_API_SECRET",
  ]
  worker_secret_keys = concat(local.api_secret_keys, ["OPENAI_API_KEY"])
  common_env = [
    { name = "APP_ENV", value = "production" },
    { name = "LOG_LEVEL", value = "INFO" },
    { name = "AWS_EMF_NAMESPACE", value = "MerchantOS/${var.name}" },
    { name = "SQS_REGION", value = var.region },
    { name = "SQS_QUEUE_NAME", value = var.queue_name },
    { name = "SQS_QUEUE_URL", value = var.queue_url },
    { name = "WEB_ORIGIN", value = var.web_origin },
    { name = "API_PUBLIC_BASE_URL", value = var.api_public_base_url },
    { name = "SHOPIFY_REDIRECT_URI", value = var.shopify_redirect_uri },
    { name = "LLM_PROVIDER", value = var.llm_provider },
  ]
}

resource "aws_ecs_task_definition" "edge" {
  count                    = var.enable_services ? 1 : 0
  family                   = "${var.name}-edge"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.api_role_arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }
  container_definitions = jsonencode([
    {
      name      = "caddy"
      image     = var.caddy_image
      essential = true
      portMappings = [
        { containerPort = 80, protocol = "tcp" },
        { containerPort = 443, protocol = "tcp" },
      ]
      environment = [
        { name = "SITE_ADDRESS", value = var.site_address },
      ]
      dependsOn = [
        { containerName = "api", condition = "HEALTHY" },
        { containerName = "web", condition = "START" },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.this["edge"].name
          awslogs-region        = var.region
          awslogs-stream-prefix = "caddy"
        }
      }
    },
    {
      name        = "api"
      image       = var.api_image
      essential   = true
      environment = local.common_env
      secrets = [
        for key in local.api_secret_keys : {
          name      = key
          valueFrom = "${var.secret_arn}:${key}::"
        }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.this["edge"].name
          awslogs-region        = var.region
          awslogs-stream-prefix = "api"
        }
      }
      healthCheck = {
        command     = ["CMD-SHELL", "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')\""]
        interval    = 15
        timeout     = 5
        retries     = 3
        startPeriod = 20
      }
    },
    {
      name      = "web"
      image     = var.web_image
      essential = true
      environment = [
        { name = "API_UPSTREAM", value = "http://127.0.0.1:8000" },
        # Fargate sets HOSTNAME to the task DNS name; Next then binds only there
        # and Caddy's 127.0.0.1:3000 proxy gets connection refused.
        { name = "HOSTNAME", value = "0.0.0.0" },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          awslogs-group         = aws_cloudwatch_log_group.this["edge"].name
          awslogs-region        = var.region
          awslogs-stream-prefix = "web"
        }
      }
      healthCheck = {
        command     = ["CMD-SHELL", "node -e \"fetch('http://127.0.0.1:3000/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))\""]
        interval    = 15
        timeout     = 5
        retries     = 3
        startPeriod = 25
      }
    }
  ])
}

resource "aws_ecs_task_definition" "worker" {
  count                    = var.enable_services ? 1 : 0
  family                   = "${var.name}-worker"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.worker_role_arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }
  container_definitions = jsonencode([{
    name        = "worker"
    image       = var.worker_image
    essential   = true
    environment = local.common_env
    secrets = [
      for key in local.worker_secret_keys : {
        name      = key
        valueFrom = "${var.secret_arn}:${key}::"
      }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.this["worker"].name
        awslogs-region        = var.region
        awslogs-stream-prefix = "worker"
      }
    }
  }])
}

resource "aws_ecs_task_definition" "migrate" {
  count                    = var.enable_services ? 1 : 0
  family                   = "${var.name}-migrate"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = var.api_role_arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }
  container_definitions = jsonencode([{
    name      = "migrate"
    image     = var.api_image
    essential = true
    command   = ["python", "-m", "merchantos_db.migrate"]
    environment = [
      { name = "APP_ENV", value = "production" },
      { name = "ALEMBIC_INI", value = "/app/packages/db/alembic.ini" },
    ]
    secrets = [
      { name = "DATABASE_URL", valueFrom = "${var.secret_arn}:MASTER_DATABASE_URL::" },
      { name = "APP_DB_PASSWORD", valueFrom = "${var.secret_arn}:APP_DB_PASSWORD::" },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.this["migrate"].name
        awslogs-region        = var.region
        awslogs-stream-prefix = "migrate"
      }
    }
  }])
}

resource "aws_ecs_service" "edge" {
  count           = var.enable_services ? 1 : 0
  name            = "edge"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.edge[0].arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = [var.public_subnet_ids[0]]
    security_groups  = [var.edge_security_group_id]
    assign_public_ip = true
  }
}

resource "aws_ecs_service" "worker" {
  count           = var.enable_services ? 1 : 0
  name            = "worker"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.worker[0].arn
  desired_count   = var.desired_count
  depends_on      = [aws_ecs_cluster_capacity_providers.this]
  capacity_provider_strategy {
    capacity_provider = "FARGATE_SPOT"
    weight            = 1
  }
  network_configuration {
    subnets          = [var.public_subnet_ids[0]]
    security_groups  = [var.worker_security_group_id]
    assign_public_ip = true
  }
}

output "cluster_name" { value = aws_ecs_cluster.this.name }
output "migrate_task_definition" { value = try(aws_ecs_task_definition.migrate[0].arn, "") }
output "public_subnet_ids" { value = var.public_subnet_ids }
output "ecs_security_group_id" { value = var.worker_security_group_id }
output "edge_service_name" { value = "edge" }
