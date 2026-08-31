from pathlib import Path

import pytest
from merchantos_db import migrate as migrate_mod
from merchantos_db.migrate import _alembic_config, _alembic_ini, _pg_quote_literal


def test_pg_quote_literal_escapes_quotes() -> None:
    assert _pg_quote_literal("plain") == "'plain'"
    assert _pg_quote_literal("o'reilly") == "'o''reilly'"


def test_pg_quote_literal_rejects_nul() -> None:
    with pytest.raises(ValueError, match="NUL"):
        _pg_quote_literal("bad\x00pass")


def test_ensure_app_role_does_not_alter_superuser_attrs() -> None:
    source = Path(migrate_mod.__file__).read_text()
    assert "ALTER ROLE merchantos_app NOSUPERUSER" not in source


def test_alembic_ini_resolves_from_repo_layout() -> None:
    path = _alembic_ini()
    assert path.is_file()
    assert path.name == "alembic.ini"
    assert (path.parent / "alembic" / "versions").is_dir()
    assert Path(path).as_posix().endswith("packages/db/alembic.ini")


def test_alembic_config_uses_ini_adjacent_scripts() -> None:
    cfg = _alembic_config("postgresql://merchantos:merchantos@localhost:5432/merchantos")
    location = Path(cfg.get_main_option("script_location"))
    assert location.is_dir()
    assert (location / "versions").is_dir()
    assert location.name == "alembic"
