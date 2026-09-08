"""기준정보 표.

거래 표(`models.py`)와 갈라 두는 이유는 **수명이 다르기** 때문이다. 기준정보는
사람이 읽고 고치는 표이고 날짜를 모른다. 거래 표는 기준일 없이는 존재할 수
없다. 값이 어디서 오는지도 그 경계를 따른다 — 기준정보의 값은
`app/seed_data/master_data.sql` 에 있고, 시나리오는 파이썬이 만든다.
"""

from __future__ import annotations

from datetime import datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core import codes
from app.db.base import Base


def _sql_value_list(names: tuple[str, ...]) -> str:
    return ", ".join(f"'{name}'" for name in names)


def _group_reference(group_code: str) -> tuple:
    """확장 표가 공통코드의 한 그룹만 참조하도록 묶는 제약 한 쌍.

    PostgreSQL 로 옮기기로 한 결정이 여기서 값을 갖는다 — 「이 칸에는 이 그룹만」을
    복합 외래키로 강제할 수 있으므로, 공통코드로 모으면서 타입이 사라진다는
    대가를 제약이 되받는다.
    """
    return (
        ForeignKeyConstraint(
            ["group_code", "code"],
            ["common_codes.group_code", "common_codes.code"],
        ),
        CheckConstraint(
            f"group_code = '{group_code}'",
            name=f"ck_{group_code.lower()}_group",
        ),
    )


class CodeGroup(Base):
    """공통코드 그룹. 프로그램이 이름으로 부르므로 화면에서 늘거나 줄지 않는다."""

    __tablename__ = "code_groups"

    group_code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    # 값이 늘 수 있는가. False 면 값마다 프로그램이 분기한다.
    value_fixed: Mapped[bool] = mapped_column(Boolean)
    description: Mapped[str] = mapped_column(String(300))

    common_codes: Mapped[list[CommonCode]] = relationship(back_populates="group")


class CommonCode(Base):
    """공통코드 본체 — 모든 분류가 함께 쓰는 것만 담는다.

    코드마다 딸린 속성은 여기 두지 않고 그 코드를 참조하는 작은 표에 둔다.
    전부 여기 밀어 넣으면 대부분이 빈 칸이 되고 `attr1 … attr9` 로 끝난다.

    삭제 칸이 없는 것은 원칙 ⑦의 코드판이다 — 지우면 그 코드로 적힌 과거 기록이
    뜻을 잃으므로, 지우는 대신 `is_active` 를 끈다. 새 기록에서는 못 고르고 옛
    기록에서는 읽힌다.
    """

    __tablename__ = "common_codes"

    group_code: Mapped[str] = mapped_column(
        ForeignKey("code_groups.group_code"), primary_key=True
    )
    # 코드값은 이름이 아니라 **주소**다. 바꾸면 과거 기록이 가리키는 것이 통째로
    # 바뀌므로 명칭은 고쳐도 코드값은 고치지 않는다.
    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    group: Mapped[CodeGroup] = relationship(back_populates="common_codes")


class TxnTypeAttribute(Base):
    """확장 ① 수불유형 — 프로그램이 이 셋을 보고 원장을 센다.

    「사유 필수」와 「승인 필요」를 넣으려다 뺐다. 사유도 승인도 수불 줄이 아니라
    근거 문서(재고조정)의 성질이며, 수불 줄은 승인이 끝난 뒤에 나는 결과다.
    """

    __tablename__ = "txn_type_attributes"
    __table_args__ = (
        *_group_reference(codes.TXN_TYPE),
        # 짝은 **이 표에 줄이 있는 수불유형**이어야 한다. 공통코드를 가리키면
        # 「그 코드가 있다」까지만 증명된다 — 속성 줄이 아예 없는 코드를 짝으로
        # 적어도 통과하고, 그러면 짝을 따라간 자리에 총량 영향도 원천 문서도
        # 없다. 여기를 가리키면 그 한 겹이 더 막힌다.
        #
        # **서로를 가리키는지까지는 제약이 보지 못한다.** A 가 B 를 짝으로 적고
        # B 는 C 를 적어도 두 줄 다 통과한다 — 같은 표의 다른 줄을 보는 조건은
        # CHECK 로 적을 수 없기 때문이다. 지금은 시드가 유일한 쓰기 경로라
        # 정합 테스트가 그것을 지키고, 화면에서 코드를 만드는 길이 생기는 날
        # 쓰기 시점 검증이나 트리거가 함께 서야 한다.
        ForeignKeyConstraint(
            ["group_code", "paired_code"],
            ["txn_type_attributes.group_code", "txn_type_attributes.code"],
        ),
        CheckConstraint(
            f"total_effect IN ({_sql_value_list(codes.TOTAL_EFFECTS)})",
            name="ck_txn_type_total_effect",
        ),
    )

    group_code: Mapped[str] = mapped_column(
        String(20), primary_key=True, default=codes.TXN_TYPE
    )
    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    total_effect: Mapped[str] = mapped_column(String(10))
    # 창고를 건너면 두 줄이 난다. 생산출고 ↔ 생산입고가 서로를 가리키므로
    # 프로그램이 짝을 함께 만든다 — 한쪽만 나는 사고를 구조가 막는다.
    paired_code: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # 원장에서 「왜 이 줄이 났는가」로 내려가는 길이고, 유형을 사람이 고르지 않는
    # 이유이기도 하다 — 화면이 유형을 정한다는 규칙의 반대 방향 기록이다.
    source_document_type: Mapped[str] = mapped_column(String(30))


class NonconformityAttribute(Base):
    """확장 ② 불합격사유 — 코드에 붙는 둘.

    계량이면 이 코드는 사람이 만들지 않는다. 검사 항목에서 따라 나오므로 연결
    칸을 두어 목록이 두 벌로 갈리지 않게 한다 — 두 벌이면 반드시 갈리고,
    항목에 「접착력」이 있는데 코드에 `FQ-ADH` 가 없으면 불합격을 적을 수가 없다.
    """

    __tablename__ = "nonconformity_attributes"
    __table_args__ = (
        *_group_reference(codes.NC_REASON),
        CheckConstraint(
            f"measure_kind IN ({_sql_value_list(codes.MEASURE_KINDS)})",
            name="ck_nonconformity_measure_kind",
        ),
        ForeignKeyConstraint(
            ["inspection_item_group", "inspection_item_code"],
            ["common_codes.group_code", "common_codes.code"],
        ),
        CheckConstraint(
            f"inspection_item_group IS NULL"
            f" OR inspection_item_group = '{codes.INSP_ITEM}'",
            name="ck_nonconformity_item_group",
        ),
        # 계량이면 반드시 어느 항목이 틀어졌는지를 가리킨다. 계수는 재는 것이
        # 아니라 세는 것이라 가리킬 측정 항목이 없을 수 있다.
        CheckConstraint(
            f"measure_kind <> '{codes.MEASURED_KIND}'"
            " OR inspection_item_code IS NOT NULL",
            name="ck_nonconformity_measured_needs_item",
        ),
        # 그룹과 코드는 함께 있거나 함께 없다. 복합 외래키는 **한 칸이라도
        # 비면 검사를 건너뛰므로**, 짝을 강제하지 않으면 「그룹은 비었고 코드만
        # 있는」 줄이 없는 검사 항목을 가리킨 채 통과한다 — 그 줄은 나중에
        # 조회에서만 터진다.
        CheckConstraint(
            "(inspection_item_group IS NULL) = (inspection_item_code IS NULL)",
            name="ck_nonconformity_item_reference_is_whole",
        ),
    )

    group_code: Mapped[str] = mapped_column(
        String(20), primary_key=True, default=codes.NC_REASON
    )
    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    measure_kind: Mapped[str] = mapped_column(String(10))
    inspection_item_group: Mapped[str | None] = mapped_column(String(20), nullable=True)
    inspection_item_code: Mapped[str | None] = mapped_column(String(30), nullable=True)


class NonconformityStageRule(Base):
    """처분 기본값은 코드가 아니라 **「코드 × 단계」**에 붙는다.

    `FQ-THK`(두께 규격 이탈)는 FQC 에서 나면 재작업이고 OQC 에서 나면 등급
    하향이다 — 같은 코드인데 처분이 다르고, 이유는 LOT 부여 시점이다.

    줄이 있는 것 자체가 「그 단계에서 쓸 수 있는 코드」라는 뜻이므로 별도의
    「적용 단계」 칸이 필요 없다 — 검사 대기를 기록의 부재로 표현한 것과 같은
    방식이다.
    """

    __tablename__ = "nonconformity_stage_rules"
    __table_args__ = (
        ForeignKeyConstraint(
            ["reason_group", "reason_code"],
            ["common_codes.group_code", "common_codes.code"],
        ),
        ForeignKeyConstraint(
            ["stage_group", "stage_code"],
            ["common_codes.group_code", "common_codes.code"],
        ),
        CheckConstraint(
            f"reason_group = '{codes.NC_REASON}'", name="ck_stage_rule_reason_group"
        ),
        CheckConstraint(
            f"stage_group = '{codes.INSP_STAGE}'", name="ck_stage_rule_stage_group"
        ),
        CheckConstraint(
            f"disposition IN ({_sql_value_list(codes.DISPOSITIONS)})",
            name="ck_stage_rule_disposition",
        ),
    )

    reason_group: Mapped[str] = mapped_column(
        String(20), primary_key=True, default=codes.NC_REASON
    )
    reason_code: Mapped[str] = mapped_column(String(30), primary_key=True)
    stage_group: Mapped[str] = mapped_column(
        String(20), primary_key=True, default=codes.INSP_STAGE
    )
    stage_code: Mapped[str] = mapped_column(String(30), primary_key=True)
    # 검사원이 코드를 고르면 다음 화면의 처분 칸이 이미 채워져 있고, 다르면
    # 바꾼다 — 원칙 ③(계산이 먼저이고 사람이 나중이다)이 품질 쪽에도 그대로다.
    disposition: Mapped[str] = mapped_column(String(20))
    # 특채는 이 설계에서 유일하게 「불합격인데 재고가 되는 길」이다.
    special_acceptance_allowed: Mapped[bool] = mapped_column(Boolean, default=False)


class PurchaseCloseAttribute(Base):
    """확장 ③ 미납 종결 사유 — 칸 셋.

    「성적 반영 여부」 칸은 두지 않는다. 성적 축이 비어 있는가로 그대로 나오기
    때문이다 — 축이 있으면 반영이고 없으면 아니다. 따로 두면 둘이 어긋날 수 있고,
    어긋나면 `PO-EOL`(단종)처럼 예외인 줄에서 어긋난다.
    """

    __tablename__ = "purchase_close_attributes"
    __table_args__ = (
        *_group_reference(codes.PO_CLOSE),
        CheckConstraint(
            f"responsibility IN ({_sql_value_list(codes.RESPONSIBILITIES)})",
            name="ck_purchase_close_responsibility",
        ),
        CheckConstraint(
            "scorecard_axis IS NULL OR scorecard_axis IN"
            f" ({_sql_value_list(codes.SCORECARD_AXES)})",
            name="ck_purchase_close_scorecard_axis",
        ),
        CheckConstraint(
            f"reorder_default IN ({_sql_value_list(codes.REORDER_DEFAULTS)})",
            name="ck_purchase_close_reorder_default",
        ),
        # 자사 사유는 공급사 성적에 잡히지 않는다. 계획이 줄어든 것을 공급사
        # 탓으로 세면 성적표가 거짓말을 한다.
        CheckConstraint(
            "responsibility = '공급사' OR scorecard_axis IS NULL",
            name="ck_purchase_close_own_fault_has_no_axis",
        ),
    )

    group_code: Mapped[str] = mapped_column(
        String(20), primary_key=True, default=codes.PO_CLOSE
    )
    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    responsibility: Mapped[str] = mapped_column(String(10))
    scorecard_axis: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reorder_default: Mapped[str] = mapped_column(String(10))


class Partner(Base):
    """거래처 — 공급사(반품 · 환불)와 고객사(수주 · 출하).

    없으면 구간 1과 5가 성립하지 않는다. 이름은 합성 데이터 원칙에 따라 가상이다.
    """

    __tablename__ = "partners"
    __table_args__ = (
        CheckConstraint(
            f"partner_type IN ({_sql_value_list(codes.PARTNER_TYPES)})",
            name="ck_partner_type",
        ),
        # `id` 는 이미 기본키라 이 유일키가 행을 더 좁히지는 않는다. 두는 이유는
        # **복합 외래키의 상대가 되기 위해서**다 — 「이 거래처는 공급사여야 한다」를
        # 참조하는 쪽에서 걸려면 `(id, 유형)` 쌍을 가리킬 수 있어야 한다.
        UniqueConstraint("id", "partner_type", name="uq_partner_id_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    partner_type: Mapped[str] = mapped_column(String(10), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ShiftPattern(Base):
    """근무 형태 셋 — 24시간 가동이라 달력이 아니라 세 줄이면 된다.

    7판의 「근무 캘린더」는 날짜를 전부 적는 표였는데, 24시간 2교대가 그것을 두
    조 + 사무 하나로 줄였다. 기준정보는 공정 조건을 알면 작아진다.

    야간조가 자정을 넘는 것이 이 표의 요점이다(21:00 → 09:00). 그래서 한 조가 두
    날짜에 걸치고, 날짜만으로는 조를 가를 수 없다.
    """

    __tablename__ = "shift_patterns"
    __table_args__ = _group_reference(codes.SHIFT)

    group_code: Mapped[str] = mapped_column(
        String(20), primary_key=True, default=codes.SHIFT
    )
    code: Mapped[str] = mapped_column(String(30), primary_key=True)
    starts_at: Mapped[time] = mapped_column(Time)
    ends_at: Mapped[time] = mapped_column(Time)
    # 현장인가 사무인가. 실사 창과 경과 시간 계산이 여기서 갈린다 — 야간에 난
    # 조정은 아침까지 승인될 수 없다(지적 ㉙).
    on_site: Mapped[bool] = mapped_column(Boolean)


class NonWorkingPeriod(Base):
    """비가동 구간 — 24시간 가동이라도 설비는 서고, 월말 실사에는 생산이 멈춘다.

    이 표만은 기준정보 SQL 에 값이 없다. 구간이 **날짜를 갖기 때문**이다 —
    「오늘」이 나오면 파이썬, 안 나오면 SQL 이라는 경계가 여기서 그어진다.
    """

    __tablename__ = "non_working_periods"

    __table_args__ = (
        # 끝이 시작보다 늦어야 구간이다. 뒤집힌 구간은 리드타임에서 **음수
        # 시간을 빼** 착수 시각을 앞이 아니라 뒤로 밀고, 길이 0 인 구간은
        # 멈춘 적이 없는 정지를 장부에 남긴다.
        CheckConstraint(
            "ends_at > starts_at",
            name="ck_non_working_period_ends_after_start",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime)
    ends_at: Mapped[datetime] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(String(100))


class ProcessInspectionStandard(Base):
    """공정별 검사 기준 — 품목 코드가 공정을 부르고, 공정이 항목을 부른다.

    한 항목이 여섯 값을 갖는다. 사람이 입력하는 것은 그 뒤의 측정값 하나뿐이고
    나머지는 전부 계산이다.

    σ 칸이 비어 있어도 조기경보의 절반은 돈다. 경고선은 규격 × 계수라 σ 와
    무관하고, WE 규칙 4(연속 8점이 중심선 같은 쪽)는 중심선 하나면 판정된다.
    그래서 초기값은 비워 두는 것이 안전하다 — 없는 것을 없다고 표시하는 편이
    가짜 Cpk 보다 낫다.
    """

    __tablename__ = "process_inspection_standards"
    __table_args__ = (
        ForeignKeyConstraint(
            ["process_group", "process_code"],
            ["common_codes.group_code", "common_codes.code"],
        ),
        ForeignKeyConstraint(
            ["item_group", "item_code"],
            ["common_codes.group_code", "common_codes.code"],
        ),
        CheckConstraint(
            f"process_group = '{codes.PROCESS}'", name="ck_standard_process_group"
        ),
        CheckConstraint(
            f"item_group = '{codes.INSP_ITEM}'", name="ck_standard_item_group"
        ),
        CheckConstraint(
            f"sigma_source IN ({_sql_value_list(codes.SIGMA_SOURCES)})",
            name="ck_standard_sigma_source",
        ),
        # 계량이면 규격 셋이 함께 있고 계수면 셋 다 없다. 계수 항목은 재는 것이
        # 아니라 세는 것이라 관리한계가 없다.
        CheckConstraint(
            "(upper_spec_limit IS NULL AND lower_spec_limit IS NULL"
            " AND center_line IS NULL)"
            " OR (upper_spec_limit IS NOT NULL AND lower_spec_limit IS NOT NULL"
            " AND center_line IS NOT NULL)",
            name="ck_standard_spec_is_all_or_nothing",
        ),
        CheckConstraint(
            "lower_spec_limit IS NULL OR lower_spec_limit < upper_spec_limit",
            name="ck_standard_spec_order",
        ),
        CheckConstraint(
            "warning_ratio > 0 AND warning_ratio <= 1",
            name="ck_standard_warning_ratio",
        ),
        # σ 가 있으면 출처가 「미정」일 수 없고, 「미정」이면 σ 가 없다. 이 칸이
        # 없으면 화면의 Cpk 가 진짜인지 자리표시자인지 아무도 모른다.
        CheckConstraint(
            f"(sigma IS NULL) = (sigma_source = '{codes.SIGMA_UNDECIDED}')",
            name="ck_standard_sigma_matches_source",
        ),
        # σ 는 표준편차라 0 이거나 음수일 수 없다. 관리한계는 이 값을 곱하고
        # Cpk 는 나누므로, 0 이면 나눗셈이 터지고 음수면 상·하한이 뒤집힌 채
        # 조용히 그려진다 — 뒤집힌 선은 아무 경보도 내지 않는다.
        CheckConstraint(
            "sigma IS NULL OR sigma > 0",
            name="ck_standard_sigma_is_positive",
        ),
    )

    process_group: Mapped[str] = mapped_column(
        String(20), primary_key=True, default=codes.PROCESS
    )
    process_code: Mapped[str] = mapped_column(String(30), primary_key=True)
    item_group: Mapped[str] = mapped_column(
        String(20), primary_key=True, default=codes.INSP_ITEM
    )
    item_code: Mapped[str] = mapped_column(String(30), primary_key=True)
    # 규격 — 고객이 준다. 넘으면 불합격이고 물건은 이미 잘못 만들어져 있다.
    upper_spec_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    lower_spec_limit: Mapped[float | None] = mapped_column(Float, nullable=True)
    center_line: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 경고선 계수 — 규격에서 긋는 사내 기준이다. 넘으면 아직 합격이지만 여유가
    # 줄었다는 뜻이며, 사내가 정하고 사내가 본다.
    warning_ratio: Mapped[float] = mapped_column(
        Float, default=codes.DEFAULT_WARNING_RATIO
    )
    # 관리한계의 σ. 규격과는 아무 관계가 없다 — 부분군 안의 변동에서 나온다.
    # 측정값이 없을 때만 쓰는 임시값이고, 부분군이 25개쯤 쌓이면 실측으로 다시
    # 그어진다. 세 선 중 시간이 지나면 스스로 바뀌는 유일한 선이다.
    sigma: Mapped[float | None] = mapped_column(Float, nullable=True)
    sigma_source: Mapped[str] = mapped_column(
        String(10), default=codes.SIGMA_UNDECIDED
    )
    # 시간이 이 값을 바꿀 수 있는가. 만료 재검사가 다시 보는 항목은 이 칸이
    # 켜진 것뿐이다 — 두께는 시간이 지나도 두께다.
    time_variant: Mapped[bool] = mapped_column(Boolean, default=False)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)


class SupplierItem(Base):
    """공급사별 품목 — 구매 기준정보.

    역산의 세 번째 겹이다. 생산 리드타임만으로는 「지금 발주해야 늦지 않는다」를
    말할 수 없다.

    칸 둘이 지적 ㉛ 때문에 붙는다. 발주는 「25kg 포대 10개」이고 재고는
    「250kg」이라 구매 단위와 재고 단위가 다른 것이 예외가 아니라 보통이다.
    단위를 섞어 저장하면 어느 값이 어느 단위인지 나중에 아무도 모르므로, 재고는
    품목의 재고 단위 하나로만 저장하고 **환산은 여기 경계에서 한 번만** 한다.
    """

    __tablename__ = "supplier_items"
    __table_args__ = (
        # 거래처는 **공급사여야 한다.** `partner_id` 만 참조하면 존재 여부만
        # 보므로 고객사가 그 자리에 들어가고, 그 줄의 리드타임과 환산 계수가
        # 구매 계획으로 흘러간다 — 물건을 팔 곳을 사 올 곳으로 쓰는 셈이다.
        # 유형 열은 데이터가 아니라 구조이며 CHECK 가 값을 못박는다(품목의
        # `stock_uom_group` 과 같은 방식).
        ForeignKeyConstraint(
            ["partner_id", "partner_type"],
            ["partners.id", "partners.partner_type"],
        ),
        CheckConstraint(
            f"partner_type = '{codes.SUPPLIER}'", name="ck_supplier_item_partner_type"
        ),
        ForeignKeyConstraint(
            ["purchase_uom_group", "purchase_uom"],
            ["common_codes.group_code", "common_codes.code"],
        ),
        CheckConstraint(
            f"purchase_uom_group = '{codes.UOM}'", name="ck_supplier_item_uom_group"
        ),
        # 리드타임은 시간으로만 저장한다(지적 ⑬). 공급사의 납기는 날로 오지만
        # 입력 시점에 일 × 24 로 바꾼다 — 두 단위를 모두 다루는 것보다 경계에서
        # 한 번 바꾸는 편이 싸다.
        CheckConstraint(
            "lead_time_hours >= 0", name="ck_supplier_item_lead_time_hours"
        ),
        CheckConstraint(
            "conversion_factor > 0", name="ck_supplier_item_conversion_factor"
        ),
    )

    partner_id: Mapped[int] = mapped_column(primary_key=True)
    partner_type: Mapped[str] = mapped_column(
        String(10), default=codes.SUPPLIER, server_default=codes.SUPPLIER
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), primary_key=True)
    lead_time_hours: Mapped[float] = mapped_column(Float)
    purchase_uom_group: Mapped[str] = mapped_column(
        String(20), default=codes.UOM
    )
    # 참조되는 칸(`common_codes.code`, 30)에 맞춘다 — 좁으면 긴 코드를
    # PostgreSQL 만 거부한다.
    purchase_uom: Mapped[str] = mapped_column(String(30))
    # 구매 단위 하나가 재고 단위로 얼마인가. 「25kg 포대」면 25.0 이다.
    conversion_factor: Mapped[float] = mapped_column(Float, default=1.0)
