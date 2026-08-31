from pathlib import Path


BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
DATABASE_PATH = BACKEND_DIRECTORY / "production_risk.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"
