from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_production_dockerfiles_are_non_root_and_secret_free() -> None:
    files = [
        ROOT / "apps/api/Dockerfile",
        ROOT / "apps/worker/Dockerfile",
        ROOT / "apps/web/Dockerfile",
        ROOT / "infra/caddy/Dockerfile",
    ]
    for path in files:
        text = path.read_text()
        assert "USER 65532" in text
        assert "COPY .env" not in text
        assert "SHOPIFY_API_SECRET=" not in text
        assert "OPENAI_API_KEY=" not in text
        if "caddy" not in path.as_posix():
            assert "AS builder" in text or "AS build" in text or "AS deps" in text


def test_edge_web_pins_hostname_so_caddy_can_reach_next() -> None:
    ecs = (ROOT / "infra/terraform/modules/ecs/main.tf").read_text()
    assert '{ name = "HOSTNAME", value = "0.0.0.0" }' in ecs


def test_staging_https_runbook_and_ip_scripts_exist() -> None:
    runbook = (ROOT / "docs/staging-https.md").read_text()
    assert "No ALB" in runbook
    assert "scripts/edge-public-ip.sh" in runbook
    ip = ROOT / "scripts/edge-public-ip.sh"
    dns = ROOT / "scripts/route53-upsert-edge-a.sh"
    assert ip.is_file() and dns.is_file()
    assert "service-name edge" in ip.read_text()
    assert "CONFIRM" in dns.read_text()
