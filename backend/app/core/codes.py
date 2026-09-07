"""공통코드 그룹 목록.

그룹은 전부 Major다 — 프로그램이 **이름으로 부르므로** 화면에서 하나도 더할
수 없고 지울 수 없다. 갈리는 것은 그룹이 아니라 그 안의 값이고, 그래서 아래
목록이 갖는 열은 「값이 늘 수 있는가」다.

값 자체는 여기 없다. 값은 `app/seed_data/master_data.sql` 에 있다 — 사람이
읽고 고치는 표이고, 코드를 몰라도 한 줄 추가로 늘릴 수 있어야 하기 때문이다.
여기 있는 것은 **프로그램이 아는 이름**뿐이며, 둘이 어긋나지 않는지는 테스트가
지킨다.

값이 고정된 그룹은 값마다 프로그램이 다른 일을 한다 — IQC 는 자재 로트를
만들고 FQC 는 완제품 로트를 만든다. 운영자가 「IQC2」를 더하면 그것을 처리할
코드가 없다. 값이 늘 수 있는 그룹은 세기만 하므로 새 라인이 생기면 공정이 늘고
새 불량이 나오면 사유가 는다 — 어느 것도 흐름을 바꾸지 않는다.
"""

from typing import NamedTuple


class CodeGroup(NamedTuple):
    """공통코드 그룹 하나의 정의."""

    group_code: str
    name: str
    # 값이 늘 수 있는가. False 면 프로그램이 값마다 분기한다.
    value_fixed: bool
    description: str


# ── 값이 고정된 그룹 ────────────────────────────────────────────────────────
WAREHOUSE = "WAREHOUSE"
STOCK_TYPE = "STOCK_TYPE"
ITEM_TYPE = "ITEM_TYPE"
TXN_TYPE = "TXN_TYPE"
INSP_STAGE = "INSP_STAGE"
ORDER_TYPE = "ORDER_TYPE"
ORDER_MODE = "ORDER_MODE"
SHIP_TYPE = "SHIP_TYPE"
ITEM_PHASE = "ITEM_PHASE"
MEAS_KIND = "MEAS_KIND"
SIGMA_SRC = "SIGMA_SRC"
WE_RULE = "WE_RULE"
SHIFT = "SHIFT"
SETTLE_TYPE = "SETTLE_TYPE"
RISK_STATUS = "RISK_STATUS"

# ── 값이 늘 수 있는 그룹 ────────────────────────────────────────────────────
NC_REASON = "NC_REASON"
PO_CLOSE = "PO_CLOSE"
SP_REASON = "SP_REASON"
ADJ_REASON = "ADJ_REASON"
PROCESS = "PROCESS"
INSP_ITEM = "INSP_ITEM"
DEPT = "DEPT"
UOM = "UOM"


CODE_GROUPS: tuple[CodeGroup, ...] = (
    CodeGroup(WAREHOUSE, "창고", True, "흐름의 구간이다. 창고를 더하면 도해가 바뀐다."),
    CodeGroup(STOCK_TYPE, "재고구분", True, "출하 가능 여부를 가른다."),
    CodeGroup(ITEM_TYPE, "품목유형", True, "BOM 전개와 검사 경로가 갈린다."),
    CodeGroup(TXN_TYPE, "수불유형", True, "부호와 재고 반영이 유형마다 다르다."),
    CodeGroup(INSP_STAGE, "검사단계", True, "단계마다 다른 일을 한다."),
    CodeGroup(ORDER_TYPE, "오더유형", True, "2단 BOM 전개의 두 자리."),
    CodeGroup(ORDER_MODE, "오더성격", True, "양산과 시양산은 오더유형과 다른 축이다."),
    CodeGroup(SHIP_TYPE, "출하유형", True, "보이는 재고가 갈린다."),
    CodeGroup(ITEM_PHASE, "품목단계", True, "게이트와 지표가 다르다(Ppk 1.67 / Cpk 1.33)."),
    CodeGroup(MEAS_KIND, "항목유형", True, "계량만 관리도에 오른다."),
    CodeGroup(SIGMA_SRC, "σ출처", True, "Cpk 를 낼지 말지를 정한다 — 「미정」이면 숫자를 내지 않는다."),
    CodeGroup(WE_RULE, "판정규칙", True, "규칙마다 계산이 다르고, 검사 기준에서 켜고 끄는 단위다."),
    CodeGroup(SHIFT, "근무형태", True, "실사 창과 경과 시간 계산이 여기서 나온다."),
    CodeGroup(SETTLE_TYPE, "반품정산", True, "대물은 물건이 돌아가고 대금은 전산상 소멸한다."),
    CodeGroup(RISK_STATUS, "경보상태", True, "risk_statuses.status 로 이미 코드에 있다."),
    CodeGroup(NC_REASON, "불합격사유", False, "계량 14는 검사 항목에서 따라 나오고 손으로 두는 것은 계수 4뿐이다."),
    CodeGroup(PO_CLOSE, "미납종결사유", False, "누구 탓인가와 그 물건이 아직 필요한가를 센다."),
    CodeGroup(SP_REASON, "특채사유", False, "불합격인데 쓰기로 한 결정의 이유."),
    CodeGroup(ADJ_REASON, "조정사유", False, "실제로 조정을 내 보아야 목록이 나온다 — 지금은 비어 있는 것이 맞다."),
    CodeGroup(PROCESS, "공정", False, "검사 항목을 고르는 라벨이다. 설비와 라우팅이 들어오면 고정 쪽으로 옮겨간다."),
    CodeGroup(INSP_ITEM, "검사항목", False, "이름만 여기 있고 규격·중심선·경고선·σ·경시변화는 (공정 × 항목) 표에 있다."),
    CodeGroup(DEPT, "부서", False, "조직의 사실. 교차 실사 기록이 이것을 요구한다."),
    CodeGroup(UOM, "단위", False, "kg · L · EA · m² — 늘어도 아무것도 고장 나지 않는다."),
)

GROUP_CODES: tuple[str, ...] = tuple(group.group_code for group in CODE_GROUPS)

# 속성은 두 층으로 가른다. 공통코드 한 표에 다 밀어 넣으면 대부분이 빈 칸이 되고
# 실무에서 흔한 `attr1 … attr9` 로 끝난다 — 「attr3이 무슨 뜻인지 아무도 모른다」가
# 그 결말이다. 그래서 본체에는 모든 분류가 함께 쓰는 것만 두고(코드 · 명칭 · 정렬 ·
# 사용 여부 · 설명), 코드마다 딸린 속성은 그 코드를 참조하는 작은 표에 둔다.
#
# 어느 그룹에 그런 표가 붙었는지는 **모델이 말한다** — `master_data._group_reference`
# 를 부르는 클래스가 그 목록이다(수불유형 · 불합격사유 · 미납종결사유 · 근무형태,
# 그리고 (공정 × 검사항목)의 검사 기준). 여기 목록을 따로 두었더니 아무 데서도
# 읽히지 않으면서 근무형태와 검사 기준이 빠진 채로 남았다 — 읽히지 않는 목록은
# 반드시 사실과 갈린다.

# ── 수불유형의 총량 영향 ────────────────────────────────────────────────────
# 「불변」은 재고구분 대체다(총량은 그대로이고 양품재고만 준다). 「기준점」은
# 전기이월이며, 잔량은 그 줄부터 더한다.
EFFECT_INCREASE = "증가"
EFFECT_DECREASE = "감소"
EFFECT_BOTH = "양방향"
EFFECT_NONE = "불변"
EFFECT_BASELINE = "기준점"
TOTAL_EFFECTS = (
    EFFECT_INCREASE,
    EFFECT_DECREASE,
    EFFECT_BOTH,
    EFFECT_NONE,
    EFFECT_BASELINE,
)

# ── 불합격 처분 ─────────────────────────────────────────────────────────────
# 「고칠 수 있는가」가 처분을 가른다 — 고칠 수 없는 것은 폐기, 쓸 수는 있는 것은
# 등급 하향이나 특채, 물건이 아니라 조건이 틀린 것은 재작업이다.
DISPOSITIONS = ("반품", "환불", "재작업", "폐기", "등급 하향")

# ── 미납 종결의 성적 축 ─────────────────────────────────────────────────────
# 비어 있으면 공급사 성적에 잡히지 않는다 — 축이 있으면 반영이고 없으면 아니다.
# 따로 「반영 여부」 칸을 두면 둘이 어긋날 수 있고, 어긋나면 예외인 줄에서 어긋난다.
SCORECARD_AXES = ("수량 준수율", "납기 준수율", "공급 가능성")
REORDER_DEFAULTS = ("필요", "불필요", "건별")
RESPONSIBILITIES = ("공급사", "자사")

# ── 검사 항목의 성질 ────────────────────────────────────────────────────────
MEASURED_KIND = "계량"
COUNTED_KIND = "계수"
MEASURE_KINDS = (MEASURED_KIND, COUNTED_KIND)

SIGMA_UNDECIDED = "미정"
SIGMA_ASSUMED = "임의"
SIGMA_OBSERVED = "실측"
SIGMA_SOURCES = (SIGMA_UNDECIDED, SIGMA_ASSUMED, SIGMA_OBSERVED)

# 경고선의 기본 계수. 규격에서 긋는 사내 기준이며 사내만 본다 — 「더 이르게 알고
# 싶다」면 0.60으로 조여도 고객에게 알릴 일이 아니다. 항목마다 다르게 둘 수
# 있도록 상수가 아니라 칸으로 만든다.
DEFAULT_WARNING_RATIO = 0.70

# ── 거래처 ──────────────────────────────────────────────────────────────────
SUPPLIER = "공급사"
CUSTOMER = "고객사"
PARTNER_TYPES = (SUPPLIER, CUSTOMER)
