import os
from pathlib import Path


BACKEND_DIRECTORY = Path(__file__).resolve().parents[2]
# 기본값은 backend/production_risk.db 이며, 컨테이너에서 볼륨에 DB를 두는 등
# 경로를 바꿔야 할 때만 DATABASE_PATH 환경변수로 재정의한다.
DATABASE_PATH = Path(
    os.environ.get("DATABASE_PATH") or BACKEND_DIRECTORY / "production_risk.db"
)

# DATABASE_URL 이 있으면 그것을 쓰고, 없으면 SQLite 파일로 떨어진다.
#
# 두 엔진을 함께 두는 이유는 값이 다르기 때문이다. 운영과 컨테이너는
# PostgreSQL 을 쓴다 — 쓰기가 늘어나고(ERP 가 되면 입고·이동·검사·출하가 전부
# 쓰기다) 타입을 강제하며 제약을 고칠 수 있어야 하기 때문이다. 반면 테스트는
# 파일 하나로 도는 편이 빠르고, 이 저장소의 제약은 두 엔진에서 같은 뜻을 갖도록
# 방언별로 컴파일된다.
DATABASE_URL = (
    os.environ.get("DATABASE_URL") or f"sqlite:///{DATABASE_PATH.as_posix()}"
)


def is_sqlite(url: str = DATABASE_URL) -> bool:
    """SQLite 인가. 연결 인자와 잠금 방식이 엔진마다 달라 이 판단이 필요하다."""
    return url.startswith("sqlite")

# 납기일이 임박했음을 알리는 완충 기간(일)
WARNING_BUFFER_DAYS = 1

RAW_MATERIAL_WAREHOUSE = "원재료창고"
PRODUCTION_WAREHOUSE = "생산창고"
PRODUCT_WAREHOUSE = "제품창고"

# 자재 로트의 보관 창고. 두 창고 재고는 모두 생산에 가용한 것으로 본다.
# 생산창고 재고를 가용에서 빼면 라인 옆에 대 놓은 자재 때문에 정상 상황이
# 부족으로 오판되기 때문이다.
MATERIAL_WAREHOUSES = (RAW_MATERIAL_WAREHOUSE, PRODUCTION_WAREHOUSE)

# 완제품 로트의 보관 창고. 생산창고가 두 목록에 모두 들어가는 것은 라인 옆에
# 투입 대기 자재와 갓 생산된 완제품이 같이 있기 때문이다. 목록을 하나로 합치면
# 자재를 제품창고에, 완제품을 원재료창고에 넣는 것을 막을 수 없다.
FINISHED_GOODS_WAREHOUSES = (PRODUCTION_WAREHOUSE, PRODUCT_WAREHOUSE)

# 창고는 셋이며 담는 것이 정해져 있다.
#   원재료창고 — 입고된 자재
#   생산창고   — 원재료창고에서 이동한 자재, 그리고 검사 대기·불합격 완제품
#   제품창고   — 출하검사 합격 완제품만
WAREHOUSES = (RAW_MATERIAL_WAREHOUSE, PRODUCTION_WAREHOUSE, PRODUCT_WAREHOUSE)

# 화면·API 주소에 쓰는 창고 코드. 한글 창고명을 URL 에 넣지 않기 위한 것이며,
# 이 사전이 유일한 대응표다.
WAREHOUSE_SLUGS: dict[str, str] = {
    "raw": RAW_MATERIAL_WAREHOUSE,
    "production": PRODUCTION_WAREHOUSE,
    "products": PRODUCT_WAREHOUSE,
}

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

# 재고구분(STOCK_TYPE). 창고 안에서 출하 가능 여부를 가르는 축이며, 창고와는
# 다른 질문에 답한다 — 창고는 「어디에 있는가」이고 재고구분은 「팔 수 있는가」다.
GOOD_STOCK = "양품"
DEFECTIVE_STOCK = "불량품"
STOCK_TYPES = (GOOD_STOCK, DEFECTIVE_STOCK)

# ── 품목 (지적 ⑧ · ⑯ · ㉛) ────────────────────────────────────────────────
# 품목 표가 하나가 되면서 「무엇인가」를 유형이 말한다. 반제품은 만들어지면서
# 쓰이므로 표가 둘일 때는 앉을 자리가 없었다.
FINISHED_ITEM = "완제품"
SEMI_FINISHED_ITEM = "반제품"
RAW_ITEM = "원자재"
ITEM_TYPES = (FINISHED_ITEM, SEMI_FINISHED_ITEM, RAW_ITEM)

# 코드 접두는 유형과 유일성만 맡는다(지적 ⑯). 공정은 접두가 아니라 별도 열이다 —
# 접두에 공정을 담으면 공정이 바뀔 때 코드를 바꿔야 하는데, 코드는 바뀌지 않는
# 것이어야 하기 때문이다.
ITEM_CODE_PREFIXES: dict[str, str] = {
    FINISHED_ITEM: "FG-",
    SEMI_FINISHED_ITEM: "SF-",
    RAW_ITEM: "RM-",
}

# 공정 다섯(PROCESS). 이 설계에서 공정은 검사 항목을 고르기 위한 라벨이며
# 설비도 라우팅도 아니다. 설비가 들어오는 날 이 목록의 성격이 바뀐다.
#
# 여기 있는 것은 **프로그램이 이름으로 부르는 공정**이지 허용값 전부가 아니다.
# 공정은 늘 수 있는 그룹이라(`codes.CODE_GROUPS`) 허용값은 공통코드에 있고,
# 품목은 그것을 복합 외래키로 가리킨다 — 이 튜플에 없는 공정도 코드에 있으면
# 쓸 수 있다.
INCOMING_PROCESS = "수입"
BLENDING_PROCESS = "배합"
COATING_PROCESS = "코팅"
LAMINATING_PROCESS = "적층경화"
SHIPPING_PROCESS = "출하"
PROCESSES = (
    INCOMING_PROCESS,
    BLENDING_PROCESS,
    COATING_PROCESS,
    LAMINATING_PROCESS,
    SHIPPING_PROCESS,
)

# 재고 단위(지적 ㉛). 잔량을 「수불의 합」으로 내린 이상 합할 수 있으려면 단위가
# 하나여야 한다. 품목에 재고 단위를 못박고 모든 수량을 그것으로 저장하며,
# 구매 단위와의 환산은 공급사별 품목에서 경계 한 번만 한다.
#
# 공정과 마찬가지로 허용값 목록이 아니다 — 단위도 늘 수 있는 그룹이고, 허용값은
# 공통코드에 있다. 못박는 것은 「품목마다 하나」이지 「이 넷 중 하나」가 아니다.
UNITS_OF_MEASURE = ("EA", "kg", "L", "m2")

# 품목단계(ITEM_PHASE). 게이트와 지표가 다르다 — 초기는 Ppk 1.67, 양산은 Cpk 1.33.
INITIAL_PHASE = "초기"
MASS_PRODUCTION_PHASE = "양산"
ITEM_PHASES = (INITIAL_PHASE, MASS_PRODUCTION_PHASE)

# BOM 은 2단으로 고정한다. 「단계」 열이 값을 1·2 로 묶어 표가 무한히 깊어지는
# 것을 막는다.
#
# 설계가 뜻한 단계의 의미는 「1단 — 완제품 ← 반제품」과 「2단 — 반제품 ←
# 원자재」다. **그러나 스키마는 아직 그것을 강제하지 않는다** — 지금 제약은
# 값이 1 이나 2 인지와 상위·하위가 같지 않은지만 본다. 그래서 `FG→SF`(1단)와
# `SF→FG`(2단) 같은 순환도 통과하고, 시드는 반제품이 없어 `완제품 ← 원자재`
# 를 1단으로 넣고 있다.
#
# 강제하려면 `items` 에 `(id, item_type)` 유일키를 두고 참조하는 표마다 유형
# 열을 더해 복합 외래키로 묶어야 한다. 그것은 **반제품 데이터와 첫 쓰기 경로가
# 생기는 단계의 일**이라 여기서는 하지 않는다 — 규칙을 상수로 적어 두기만 하면
# 지켜지는 것처럼 보이므로, 적어 두지 않고 이 주석으로 남긴다.
BOM_LEVELS = (1, 2)
