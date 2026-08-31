from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_staging_network_is_least_privilege() -> None:
    network = (ROOT / "infra/terraform/modules/network/main.tf").read_text()
    rds = (ROOT / "infra/terraform/modules/rds/main.tf").read_text()
    iam = (ROOT / "infra/terraform/modules/iam/main.tf").read_text()
    ecs = (ROOT / "infra/terraform/modules/ecs/main.tf").read_text()
    assert "from_port   = 80" in network
    assert "from_port   = 443" in network
    assert 'resource "aws_security_group" "worker"' in network
    worker = network.split('resource "aws_security_group" "worker"')[1]
    assert "ingress" not in worker.split("output")[0]
    assert "publicly_accessible          = false" in rds
    assert "aws_lb" not in (ROOT / "infra/terraform/modules/ecs/main.tf").read_text()
    assert "aws_nat_gateway" not in network
    assert "AdministratorAccess" not in iam
    assert "sqs:SendMessage" in iam
    api_policy = iam.split('resource "aws_iam_role_policy" "api"')[1]
    api_only = api_policy.split('resource "aws_iam_role" "worker"')[0]
    assert "secretsmanager:GetSecretValue" not in api_only
    assert "sts:AssumeRoleWithWebIdentity" in iam
    assert "environment:staging" in iam
    assert "USER 65532" in (ROOT / "apps/api/Dockerfile").read_text()
    assert "HOSTNAME" in ecs


def test_github_oidc_is_not_admin() -> None:
    iam = (ROOT / "infra/terraform/modules/iam/main.tf").read_text()
    github_policy = iam.split('resource "aws_iam_role_policy" "github"')[1]
    assert "iam:CreateUser" not in github_policy
    assert "iam:AttachRolePolicy" not in github_policy
    assert "ecr:GetAuthorizationToken" in github_policy
    assert "ecs:UpdateService" in github_policy or "ecs:RunTask" in github_policy
