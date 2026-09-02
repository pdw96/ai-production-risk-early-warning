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

# 자재 로트의 보관 창고. 두 창고 재고는 모두 생산에 가용한 것으로 본다.
# 생산창고 재고를 가용에서 빼면 라인 옆에 대 놓은 자재 때문에 정상 상황이
# 부족으로 오판되기 때문이다.
RAW_MATERIAL_WAREHOUSE = "원재료창고"
PRODUCTION_WAREHOUSE = "생산창고"
WAREHOUSES = (RAW_MATERIAL_WAREHOUSE, PRODUCTION_WAREHOUSE)
