from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_production_dockerfiles_are_non_root_and_secret_free() -> None:
    files = [
        ROOT / "apps/api/Dockerfile",
        ROOT / "apps/worker/Dockerfile",
        ROOT / "apps/web/Dockerfile",
    ]
    for path in files:
        text = path.read_text()
        assert "USER 65532" in text
        assert "COPY .env" not in text
        assert "SHOPIFY_API_SECRET=" not in text
        assert "OPENAI_API_KEY=" not in text
        assert "AS builder" in text or "AS build" in text or "AS deps" in text
