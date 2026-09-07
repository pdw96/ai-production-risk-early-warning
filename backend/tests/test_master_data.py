"""기준정보 표와 그 값이 서로 어긋나지 않는지 지킨다.

이 파일이 지키는 것은 대부분 **목록이 두 벌이 되지 않는가**다. 파이썬 상수와
SQL 파일에 같은 목록이 따로 있으면 반드시 갈리고, 갈리면 화면에는 있는데
저장은 거부되는 값이 생긴다.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core import codes
from app.core.config import (
    ITEM_PHASES,
    ITEM_TYPES,
    PROCESSES,
    STOCK_TYPES,
    UNITS_OF_MEASURE,
    WAREHOUSES,
)
from app.db.base import Base, register_models
from app.db.master_data import (
    CodeGroup,
    CommonCode,
    NonconformityAttribute,
    NonconformityStageRule,
    NonWorkingPeriod,
    Partner,
    ProcessInspectionStandard,
    PurchaseCloseAttribute,
    ShiftPattern,
    TxnTypeAttribute,
)
from app.db.master_data_loader import load_master_data, statements


@pytest.fixture
def session() -> Session:
    # 기준정보 표는 거래 표를 참조한다(supplier_items → items). 모델을 전부
    # 등록하지 않으면 이 파일만 따로 돌릴 때 외래키가 대상을 못 찾는다.
    register_models()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as database_session:
        load_master_data(database_session)
        database_session.commit()
        yield database_session


def _codes_of(session: Session, group_code: str) -> set[str]:
    return set(
        session.scalars(
            select(CommonCode.code).where(CommonCode.group_code == group_code)
        ).all()
    )


def test_every_group_the_program_names_exists_in_the_master_data(
    session: Session,
) -> None:
    """그룹은 프로그램이 이름으로 부른다 — 없는 이름을 부르면 그 자리가 빈다."""
    stored = set(session.scalars(select(CodeGroup.group_code)).all())

    assert stored == set(codes.GROUP_CODES)


def test_groups_that_the_program_branches_on_are_marked_fixed(
    session: Session,
) -> None:
    """값이 고정된 그룹은 값마다 프로그램이 다른 일을 한다.

    운영자가 「IQC2」를 더하면 그것을 처리할 코드가 없다 — 「수정 불가」의 이유가
    규칙이 아니라 구조인 자리다.
    """
    fixed = {
        group.group_code
        for group in session.scalars(select(CodeGroup)).all()
        if group.value_fixed
    }

    assert fixed == {
        group.group_code for group in codes.CODE_GROUPS if group.value_fixed
    }
    assert codes.INSP_STAGE in fixed
    assert codes.NC_REASON not in fixed


@pytest.mark.parametrize(
    ("group_code", "constants"),
    (
        (codes.WAREHOUSE, WAREHOUSES),
        (codes.STOCK_TYPE, STOCK_TYPES),
        (codes.ITEM_TYPE, ITEM_TYPES),
        (codes.ITEM_PHASE, ITEM_PHASES),
        (codes.PROCESS, PROCESSES),
        (codes.UOM, UNITS_OF_MEASURE),
    ),
)
def test_the_code_values_agree_with_the_constants_the_program_uses(
    session: Session,
    group_code: str,
    constants: tuple[str, ...],
) -> None:
    """같은 목록이 파이썬 상수와 SQL 에 따로 있으면 반드시 갈린다.

    CHECK 제약은 상수에서 구워지고 드롭다운은 공통코드에서 나오므로, 둘이
    어긋나면 화면에는 뜨는데 저장은 거부되는 값이 생긴다.
    """
    assert _codes_of(session, group_code) == set(constants)


def test_the_ledger_knows_twelve_transaction_types_and_every_one_has_attributes(
    session: Session,
) -> None:
    """수불유형은 아무도 고르지 않는다 — 어느 화면에서 일어났는가가 정한다.

    그래서 유형마다 「근거 문서 유형」이 반드시 있어야 한다. 비어 있으면 원장에서
    「왜 이 줄이 났는가」로 내려가는 길이 끊긴다.
    """
    transaction_codes = _codes_of(session, codes.TXN_TYPE)
    attributes = session.scalars(select(TxnTypeAttribute)).all()

    assert len(transaction_codes) == 12
    assert {row.code for row in attributes} == transaction_codes
    assert all(row.source_document_type for row in attributes)


def test_transaction_pairs_point_at_each_other(session: Session) -> None:
    """창고를 건너면 두 줄이 난다. 짝이 서로를 가리켜야 한쪽만 나는 사고를
    구조가 막는다."""
    paired = {
        row.code: row.paired_code
        for row in session.scalars(select(TxnTypeAttribute)).all()
        if row.paired_code is not None
    }

    assert paired
    for code, partner in paired.items():
        assert paired[partner] == code


def test_exactly_one_transaction_type_is_the_baseline(session: Session) -> None:
    """전기이월만이 기준점이다 — 잔량은 그 줄부터 더한다. 둘이면 어디서부터
    더할지 알 수 없다."""
    baselines = [
        row.code
        for row in session.scalars(select(TxnTypeAttribute)).all()
        if row.total_effect == codes.EFFECT_BASELINE
    ]

    assert baselines == ["전기이월"]


def test_every_measured_nonconformity_points_at_an_inspection_item(
    session: Session,
) -> None:
    """목록을 두 벌 두지 않는다 — 계량 코드는 검사 항목에서 따라 나온다.

    항목에 「접착력」을 넣고 코드 표에 FQ-ADH 를 안 넣으면 불합격을 적을 수가
    없고, 반대로 하면 쓰이지 않는 코드가 남는다.
    """
    attributes = session.scalars(select(NonconformityAttribute)).all()
    item_codes = _codes_of(session, codes.INSP_ITEM)

    measured = [row for row in attributes if row.measure_kind == codes.MEASURED_KIND]
    assert len(measured) == 14
    assert all(row.inspection_item_code in item_codes for row in measured)


def test_the_inspection_item_list_is_fourteen_measured_and_four_counted(
    session: Session,
) -> None:
    """계량만 관리도에 오른다. 계수는 재는 것이 아니라 세는 것이다."""
    assert len(_codes_of(session, codes.INSP_ITEM)) == 18

    counted = [
        row
        for row in session.scalars(select(NonconformityAttribute)).all()
        if row.measure_kind == codes.COUNTED_KIND
    ]
    # 계수 다섯 중 하나(IQ-EXP)는 사람이 보는 게 아니라 시스템이 입고일에서
    # 계산해 자동으로 다는 것이라 가리킬 측정 항목이 없다.
    assert len(counted) == 5
    assert [row.code for row in counted if row.inspection_item_code is None] == [
        "IQ-EXP"
    ]


def test_the_same_code_gets_a_different_disposition_at_a_different_stage(
    session: Session,
) -> None:
    """처분 기본값은 코드가 아니라 「코드 × 단계」에 붙는다.

    FQ-THK 는 FQC 에서 나면 재작업이고 OQC 에서 나면 등급 하향이다 — 같은
    코드인데 처분이 다르고, 이유는 LOT 부여 시점이다.
    """
    dispositions = {
        row.stage_code: row.disposition
        for row in session.scalars(
            select(NonconformityStageRule).where(
                NonconformityStageRule.reason_code == "FQ-THK"
            )
        ).all()
    }

    assert dispositions == {"FQC": "재작업", "OQC": "등급 하향"}


def test_the_only_stages_a_code_may_be_used_in_are_the_rows_that_exist(
    session: Session,
) -> None:
    """줄이 있는 것 자체가 「그 단계에서 쓸 수 있는 코드」라는 뜻이므로 별도의
    「적용 단계」 칸이 필요 없다 — 검사 대기를 기록의 부재로 표현한 것과 같다."""
    stages_by_prefix: dict[str, set[str]] = {}
    for row in session.scalars(select(NonconformityStageRule)).all():
        stages_by_prefix.setdefault(row.reason_code[:3], set()).add(row.stage_code)

    assert stages_by_prefix == {
        "IQ-": {"IQC"},
        "IP-": {"IPQC"},
        "FQ-": {"FQC", "OQC"},
    }


def test_special_acceptance_is_allowed_only_where_the_goods_are_usable(
    session: Session,
) -> None:
    """특채는 이 설계에서 유일하게 「불합격인데 재고가 되는 길」이다."""
    allowed = {
        row.reason_code
        for row in session.scalars(select(NonconformityStageRule)).all()
        if row.special_acceptance_allowed
    }

    assert allowed == {"IQ-VIS", "IQ-COL", "IQ-DOC"}


def test_an_own_fault_close_reason_never_lands_on_the_supplier_scorecard(
    session: Session,
) -> None:
    """성적 축이 비어 있는가로 반영 여부가 그대로 나온다 — 따로 칸을 두면 둘이
    어긋나고, 어긋나면 PO-EOL 처럼 예외인 줄에서 어긋난다."""
    rows = {
        row.code: row
        for row in session.scalars(select(PurchaseCloseAttribute)).all()
    }

    assert len(rows) == 7
    assert all(
        row.scorecard_axis is None
        for row in rows.values()
        if row.responsibility == "자사"
    )
    # 단종은 공급사 쪽인데 축이 비어 있다 — 공급사의 잘못이 아니기 때문이다.
    assert rows["PO-EOL"].responsibility == "공급사"
    assert rows["PO-EOL"].scorecard_axis is None


def test_the_night_shift_crosses_midnight(session: Session) -> None:
    """야간조는 21시에 시작해 다음 날 09시에 끝난다 — 한 조가 두 날짜에 걸친다.

    그래서 날짜만으로는 조를 가를 수 없고, 검사 기록이 시각을 가져야 한다.
    """
    shifts = {row.code: row for row in session.scalars(select(ShiftPattern)).all()}

    assert set(shifts) == {"DAY", "NIGHT", "OFFICE"}
    assert shifts["NIGHT"].starts_at > shifts["NIGHT"].ends_at
    assert shifts["OFFICE"].on_site is False
    assert shifts["DAY"].on_site is True


def test_the_on_site_shifts_cover_the_whole_day_without_a_gap(
    session: Session,
) -> None:
    """24시간 가동이라 교대 띠에 빈칸이 없다. 이것이 달력을 지운 조건이다."""
    on_site = [
        row for row in session.scalars(select(ShiftPattern)).all() if row.on_site
    ]

    assert len(on_site) == 2
    day, night = sorted(on_site, key=lambda row: row.starts_at)
    assert day.ends_at == night.starts_at
    assert night.ends_at == day.starts_at


def test_every_inspection_standard_belongs_to_a_real_process_and_item(
    session: Session,
) -> None:
    """품목 코드가 공정을 부르고 공정이 항목을 부른다. 어느 쪽이든 없는 것을
    가리키면 검사 화면이 기준을 끌어오지 못한다."""
    standards = session.scalars(select(ProcessInspectionStandard)).all()
    processes = _codes_of(session, codes.PROCESS)
    items = _codes_of(session, codes.INSP_ITEM)

    assert standards
    assert {row.process_code for row in standards} == processes
    assert all(row.item_code in items for row in standards)


def test_sigma_starts_empty_so_that_no_fake_capability_index_is_shown(
    session: Session,
) -> None:
    """규격에서 뽑은 σ 는 어떤 계수를 쓰든 Cpk 를 상수로 만든다.

    공정이 좋아지든 나빠지든 화면의 숫자가 움직이지 않으므로, 없는 것을 없다고
    표시하는 편이 가짜 Cpk 보다 낫다. 그래도 경고선과 WE 규칙 4 는 그대로 돈다 —
    둘 다 σ 를 쓰지 않기 때문이다.
    """
    standards = session.scalars(select(ProcessInspectionStandard)).all()

    assert all(row.sigma is None for row in standards)
    assert all(row.sigma_source == codes.SIGMA_UNDECIDED for row in standards)
    assert all(row.warning_ratio == codes.DEFAULT_WARNING_RATIO for row in standards)


def test_counted_items_carry_no_specification_limits(session: Session) -> None:
    """계수 항목은 재는 것이 아니라 세는 것이라 관리한계가 없다."""
    counted_items = {
        row.inspection_item_code
        for row in session.scalars(select(NonconformityAttribute)).all()
        if row.measure_kind == codes.COUNTED_KIND and row.inspection_item_code
    }
    standards = session.scalars(select(ProcessInspectionStandard)).all()

    for row in standards:
        if row.item_code in counted_items:
            assert row.upper_spec_limit is None
            assert row.center_line is None
        else:
            assert row.upper_spec_limit is not None
            assert row.lower_spec_limit < row.center_line < row.upper_spec_limit


def test_only_time_variant_items_come_back_for_a_retest(session: Session) -> None:
    """만료 재검사가 다시 보는 항목은 이 칸이 켜진 것뿐이다 — 잣대는 하나이고
    「시간이 이 값을 바꿀 수 있는가」다. 두께는 시간이 지나도 두께다."""
    time_variant = {
        row.item_code
        for row in session.scalars(select(ProcessInspectionStandard)).all()
        if row.time_variant
    }

    assert time_variant == {"IT-MOI", "IT-VIS", "IT-MVS", "IT-ADH"}


def test_the_adjustment_reason_list_is_deliberately_empty(session: Session) -> None:
    """실제로 조정을 내 보아야 목록이 나온다. 미리 채우면 없는 것이 있는 것처럼
    보이고, 빈 기준정보는 없는 기준정보보다 나쁘다."""
    assert _codes_of(session, codes.ADJ_REASON) == set()


def test_partners_cover_both_ends_of_the_flow(session: Session) -> None:
    """공급사가 없으면 구간 1이, 고객사가 없으면 구간 5가 성립하지 않는다."""
    partners = session.scalars(select(Partner)).all()

    assert {row.partner_type for row in partners} == {codes.SUPPLIER, codes.CUSTOMER}


def test_a_code_may_be_retired_but_not_deleted(session: Session) -> None:
    """원칙 ⑦의 코드판 — 지우면 그 코드로 적힌 과거 기록이 뜻을 잃는다.

    「사용 중지」로 두면 새 기록에서는 못 고르고 옛 기록에서는 읽힌다.
    """
    retired = session.get(CommonCode, (codes.NC_REASON, "IQ-DOC"))
    retired.is_active = False
    session.commit()

    assert session.get(CommonCode, (codes.NC_REASON, "IQ-DOC")) is not None
    assert session.scalar(
        select(func.count())
        .select_from(CommonCode)
        .where(CommonCode.group_code == codes.NC_REASON)
    ) == 19


def test_an_extension_row_cannot_reach_into_another_group(session: Session) -> None:
    """복합 외래키가 「이 칸에는 이 그룹만」을 강제한다.

    공통코드로 모으면 타입이 사라진다는 대가를 제약이 되받는 자리다.
    """
    session.add(
        PurchaseCloseAttribute(
            group_code=codes.PO_CLOSE,
            # 불합격 사유 코드다 — 미납 종결 그룹에는 없다.
            code="IQ-FM",
            responsibility="공급사",
            scorecard_axis=None,
            reorder_default="필요",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_a_standard_cannot_claim_an_observed_sigma_without_a_value(
    session: Session,
) -> None:
    """σ 출처가 없으면 화면의 Cpk 가 진짜인지 자리표시자인지 아무도 모른다."""
    session.add(
        ProcessInspectionStandard(
            process_group=codes.PROCESS,
            process_code="출하",
            item_group=codes.INSP_ITEM,
            item_code="IT-COL",
            upper_spec_limit=1.0,
            lower_spec_limit=0.0,
            center_line=0.3,
            warning_ratio=codes.DEFAULT_WARNING_RATIO,
            sigma=None,
            sigma_source=codes.SIGMA_OBSERVED,
            time_variant=False,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_statement_splitting_survives_a_semicolon_inside_a_description() -> None:
    """설명 칸에는 한글 문장이 들어간다. 거기 세미콜론이 한 번이라도 섞이면
    조용히 반 토막 난 SQL 이 실행된다."""
    sql = """
    -- 주석은 걷어낸다; 여기 세미콜론이 있어도 문장이 아니다
    INSERT INTO t (a) VALUES ('세미콜론; 하나'); -- 꼬리 주석
    INSERT INTO t (a) VALUES ('따옴표'' 하나');
    """

    assert statements(sql) == [
        "INSERT INTO t (a) VALUES ('세미콜론; 하나')",
        "INSERT INTO t (a) VALUES ('따옴표'' 하나')",
    ]


# ══════════════════════════════════════════════════════════════════════════
# 리뷰가 찾아낸 제약의 구멍 넷. 넷 다 「스키마가 허용하는데 읽는 쪽이 터지는」
# 모양이라, 값이 들어간 뒤 조회에서야 드러난다 — 그래서 넣는 자리에서 막는다.
# ══════════════════════════════════════════════════════════════════════════


def test_a_measured_reason_cannot_point_at_half_an_inspection_item(
    session: Session,
) -> None:
    """복합 외래키는 한 칸이라도 비면 검사를 건너뛴다.

    그래서 「그룹은 비었고 코드만 있는」 줄은 없는 검사 항목을 가리킨 채로
    통과해 버린다. 짝을 강제하지 않으면 외래키가 있어도 지켜 주지 않는다.
    """
    session.add(
        NonconformityAttribute(
            code="IQ-XXX",
            measure_kind=codes.MEASURED_KIND,
            inspection_item_group=None,
            inspection_item_code="두께",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_sigma_cannot_be_zero_or_negative(session: Session) -> None:
    """σ 는 표준편차다. 0 이면 Cpk 의 나눗셈이 터지고, 음수면 관리한계가
    뒤집힌 채 조용히 그려진다 — 뒤집힌 선은 아무 경보도 내지 않는다."""
    session.add(
        ProcessInspectionStandard(
            process_code=PROCESSES[0],
            item_code="두께",
            upper_spec_limit=10.0,
            lower_spec_limit=5.0,
            center_line=7.5,
            sigma=0.0,
            sigma_source=codes.SIGMA_ASSUMED,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_a_non_working_period_cannot_end_before_it_starts(session: Session) -> None:
    """뒤집힌 구간은 리드타임에서 음수 시간을 빼 착수 시각을 뒤로 민다."""
    session.add(
        NonWorkingPeriod(
            starts_at=datetime(2026, 9, 30, 17, 30),
            ends_at=datetime(2026, 9, 30, 9, 0),
            reason="뒤집힌 구간",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_a_zero_length_non_working_period_is_not_an_outage(session: Session) -> None:
    """길이가 0 인 구간은 멈춘 적이 없는 정지를 장부에 남긴다."""
    session.add(
        NonWorkingPeriod(
            starts_at=datetime(2026, 9, 30, 9, 0),
            ends_at=datetime(2026, 9, 30, 9, 0),
            reason="길이 없는 구간",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
