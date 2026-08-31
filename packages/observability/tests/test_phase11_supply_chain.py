from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

FORBIDDEN_PY = (
    "pycrypto==",
    "eval(",
)
FORBIDDEN_NPM = (
    "event-stream",
    "flatmap-stream",
)


def test_lockfiles_exist_and_omit_known_malicious_packages() -> None:
    uv_lock = (ROOT / "uv.lock").read_text()
    pkg = (ROOT / "apps/web/package.json").read_text()
    assert (ROOT / "apps/web/pnpm-lock.yaml").is_file() or (ROOT / "pnpm-lock.yaml").is_file()
    for needle in FORBIDDEN_PY:
        assert needle not in uv_lock
    blob = pkg
    lock = ROOT / "pnpm-lock.yaml"
    if lock.is_file():
        blob += lock.read_text()
    web_lock = ROOT / "apps/web/pnpm-lock.yaml"
    if web_lock.is_file():
        blob += web_lock.read_text()
    for needle in FORBIDDEN_NPM:
        assert needle not in blob
    assert "merchantos-agents" in uv_lock
    root = (ROOT / "package.json").read_text()
    assert '"postcss": ">=8.5.23"' in root
