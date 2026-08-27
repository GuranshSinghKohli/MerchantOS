terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 5.80"
    }
  }
}

variable "name" { type = string }
variable "vpc_id" { type = string }
variable "public_subnet_ids" { type = list(string) }
variable "alb_security_group_id" { type = string }
variable "ecs_security_group_id" { type = string }
variable "execution_role_arn" { type = string }
variable "api_role_arn" { type = string }
variable "worker_role_arn" { type = string }
variable "api_image" { type = string }
variable "worker_image" { type = string }
variable "web_image" { type = string }
variable "secret_arn" { type = string }
variable "queue_name" { type = string }
variable "queue_url" { type = string }
variable "region" { type = string }
variable "web_origin" { type = string }
variable "api_public_base_url" { type = string }
variable "shopify_redirect_uri" { type = string }
variable "enable_https" { type = bool }
variable "certificate_arn" { type = string }
variable "desired_count" { type = number }
variable "enable_services" { type = bool }
variable "llm_provider" { type = string }

resource "aws_cloudwatch_log_group" "this" {
  for_each          = toset(["api", "worker", "web", "migrate"])
  name              = "/merchantos/${var.name}/${each.key}"
  retention_in_days = 7
}

resource "aws_lb" "this" {
  name               = substr(var.name, 0, 32)
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids
}

resource "aws_lb_target_group" "api" {
  name        = "${substr(var.name, 0, 18)}-api"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"
  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 15
  }
}

resource "aws_lb_target_group" "web" {
  name        = "${substr(var.name, 0, 18)}-web"
  port        = 3000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"
  health_check {
    path                = "/health"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 15
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type = var.enable_https ? "redirect" : "forward"
    dynamic "redirect" {
      for_each = var.enable_https ? [1] : []
      content {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
    dynamic "forward" {
      for_each = var.enable_https ? [] : [1]
      content {
        target_group {
          arn = aws_lb_target_group.web.arn
        }
      }
    }
  }
}

resource "aws_lb_listener" "https" {
  count             = var.enable_https ? 1 : 0
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  certificate_arn   = var.certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
}

resource "aws_lb_listener_rule" "api_http" {
  count        = var.enable_https ? 0 : 1
  listener_arn = aws_lb_listener.http.arn
  priority     = 10
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  condition {
    path_pattern { values = ["/api/*", "/health", "/ready", "/ready/*"] }
  }
}

resource "aws_lb_listener_rule" "api_https" {
  count        = var.enable_https ? 1 : 0
  listener_arn = aws_lb_listener.https[0].arn
  priority     = 10
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
  condition {
    path_pattern { values = ["/api/*", "/health", "/ready", "/ready/*"] }
  }
}

resource "aws_ecs_cluster" "this" {
  name = var.name
  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}

resource "aws_service_discovery_private_dns_namespace" "this" {
  name = "${var.name}.internal"
  vpc  = var.vpc_id
}

resource "aws_service_discovery_service" "api" {
  name = "api"
  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.this.id
    dns_records {
      ttl  = 10
      type = "A"
    }
  }
}

locals {
  api_secret_keys = [
    "DATABASE_URL",
    "REDIS_URL",
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

resource "aws_ecs_task_definition" "api" {
  count                    = var.enable_services ? 1 : 0
  family                   = "${var.name}-api"
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
    name         = "api"
    image        = var.api_image
    essential    = true
    portMappings = [{ containerPort = 8000, protocol = "tcp" }]
    environment  = local.common_env
    secrets = [
      for key in local.api_secret_keys : {
        name      = key
        valueFrom = "${var.secret_arn}:${key}::"
      }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.this["api"].name
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
  }])
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

resource "aws_ecs_task_definition" "web" {
  count                    = var.enable_services ? 1 : 0
  family                   = "${var.name}-web"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = var.execution_role_arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }
  container_definitions = jsonencode([{
    name         = "web"
    image        = var.web_image
    essential    = true
    portMappings = [{ containerPort = 3000, protocol = "tcp" }]
    environment = [
      { name = "API_UPSTREAM", value = "http://api.${var.name}.internal:8000" },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.this["web"].name
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

resource "aws_ecs_service" "api" {
  count           = var.enable_services ? 1 : 0
  name            = "api"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.api[0].arn
  depends_on      = [aws_lb_listener.http]
  desired_count   = var.desired_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [var.ecs_security_group_id]
    assign_public_ip = true
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }
  service_registries {
    registry_arn = aws_service_discovery_service.api.arn
  }
}

resource "aws_ecs_service" "worker" {
  count           = var.enable_services ? 1 : 0
  name            = "worker"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.worker[0].arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [var.ecs_security_group_id]
    assign_public_ip = true
  }
}

resource "aws_ecs_service" "web" {
  count           = var.enable_services ? 1 : 0
  name            = "web"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.web[0].arn
  depends_on      = [aws_lb_listener.http]
  desired_count   = var.desired_count
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [var.ecs_security_group_id]
    assign_public_ip = true
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.web.arn
    container_name   = "web"
    container_port   = 3000
  }
}

output "alb_dns_name" { value = aws_lb.this.dns_name }
output "cluster_name" { value = aws_ecs_cluster.this.name }
output "migrate_task_definition" { value = try(aws_ecs_task_definition.migrate[0].arn, "") }
output "alb_arn_suffix" { value = aws_lb.this.arn_suffix }
output "api_target_group_arn_suffix" { value = aws_lb_target_group.api.arn_suffix }
output "public_subnet_ids" { value = var.public_subnet_ids }
output "ecs_security_group_id" { value = var.ecs_security_group_id }
