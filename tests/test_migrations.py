from pathlib import Path
from alembic.config import Config
from alembic import command
import pytest


def test_alembic_migrations_upgrade_and_downgrade(tmp_path: Path):
    """Verify that all Alembic migrations upgrade to head and downgrade to base cleanly."""
    db_file = tmp_path / "migration_test.db"
    db_url = f"sqlite:///{db_file}"

    backend_dir = Path(__file__).resolve().parents[1]
    alembic_ini_path = backend_dir / "alembic.ini"

    alembic_cfg = Config(str(alembic_ini_path))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)
    alembic_cfg.set_main_option("script_location", str(backend_dir / "migrations"))

    # Upgrade to head
    command.upgrade(alembic_cfg, "head")

    # Downgrade back to base
    command.downgrade(alembic_cfg, "base")

    # Re-upgrade to head
    command.upgrade(alembic_cfg, "head")
