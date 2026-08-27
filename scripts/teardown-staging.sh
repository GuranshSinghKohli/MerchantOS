#!/usr/bin/env bash
set -euo pipefail
# Destroys the staging Terraform stack. Production is not targeted.
cd "$(dirname "$0")/../infra/terraform/envs/staging"
terraform destroy "$@"
