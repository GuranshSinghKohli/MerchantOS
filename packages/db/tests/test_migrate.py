from pathlib import Path

from merchantos_db.migrate import _alembic_ini


def test_alembic_ini_resolves_from_repo_layout() -> None:
    path = _alembic_ini()
    assert path.is_file()
    assert path.name == "alembic.ini"
    assert (path.parent / "alembic" / "versions").is_dir()
    assert Path(path).as_posix().endswith("packages/db/alembic.ini")
