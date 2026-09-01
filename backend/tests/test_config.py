import importlib
from pathlib import Path

import pytest

from app.core import config


@pytest.fixture(autouse=True)
def restore_config_module():
    """환경변수를 바꿔 모듈을 다시 읽었으므로 다른 테스트를 위해 원상복구한다."""
    yield
    importlib.reload(config)


def test_database_path_defaults_to_backend_directory(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    reloaded = importlib.reload(config)

    assert reloaded.DATABASE_PATH == reloaded.BACKEND_DIRECTORY / "production_risk.db"
    assert reloaded.DATABASE_URL.startswith("sqlite:///")


def test_database_path_can_be_overridden_by_environment(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_PATH", "/data/production_risk.db")
    reloaded = importlib.reload(config)

    assert reloaded.DATABASE_PATH == Path("/data/production_risk.db")
    assert reloaded.DATABASE_URL == "sqlite:////data/production_risk.db"
