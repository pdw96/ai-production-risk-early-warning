from pathlib import Path


BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
DATABASE_PATH = BACKEND_DIRECTORY / "production_risk.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

# 납기일이 임박했음을 알리는 완충 기간(일)
WARNING_BUFFER_DAYS = 1
