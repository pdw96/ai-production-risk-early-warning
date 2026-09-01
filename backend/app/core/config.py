import os
from pathlib import Path


BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
# 기본값은 backend/production_risk.db 이며, 컨테이너에서 볼륨에 DB를 두는 등
# 경로를 바꿔야 할 때만 DATABASE_PATH 환경변수로 재정의한다.
DATABASE_PATH = Path(
    os.environ.get("DATABASE_PATH") or BACKEND_DIRECTORY / "production_risk.db"
)
DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

# 납기일이 임박했음을 알리는 완충 기간(일)
WARNING_BUFFER_DAYS = 1
