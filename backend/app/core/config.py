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

RAW_MATERIAL_WAREHOUSE = "원재료창고"
PRODUCTION_WAREHOUSE = "생산창고"
FINISHED_GOODS_WAREHOUSE = "완제품창고"

# 자재 로트의 보관 창고. 두 창고 재고는 모두 생산에 가용한 것으로 본다.
# 생산창고 재고를 가용에서 빼면 라인 옆에 대 놓은 자재 때문에 정상 상황이
# 부족으로 오판되기 때문이다.
MATERIAL_WAREHOUSES = (RAW_MATERIAL_WAREHOUSE, PRODUCTION_WAREHOUSE)

# 완제품 로트의 보관 창고. 생산창고가 두 목록에 모두 들어가는 것은 라인 옆에
# 투입 대기 자재와 갓 생산된 완제품이 같이 있기 때문이다. 목록을 하나로 합치면
# 자재를 완제품창고에, 완제품을 원재료창고에 넣는 것을 막을 수 없다.
FINISHED_GOODS_WAREHOUSES = (PRODUCTION_WAREHOUSE, FINISHED_GOODS_WAREHOUSE)

# 완제품 로트의 출하검사(OQC) 상태. 검사 기록이 없는 로트가 `검사 대기`다.
QC_PENDING = "검사 대기"
QC_PASSED = "합격"
QC_FAILED = "불합격"
QC_STATUSES = (QC_PENDING, QC_PASSED, QC_FAILED)

# 검사 유형과 판정. 판정에 `검사 대기`가 없는 것은 검사를 하지 않은 것이
# 판정이 아니기 때문이다 — 기록이 없는 상태로 표현한다.
INCOMING_INSPECTION = "IQC"
PROCESS_INSPECTION = "PQC"
OUTGOING_INSPECTION = "OQC"
INSPECTION_TYPES = (INCOMING_INSPECTION, PROCESS_INSPECTION, OUTGOING_INSPECTION)
INSPECTION_RESULTS = (QC_PASSED, QC_FAILED)
