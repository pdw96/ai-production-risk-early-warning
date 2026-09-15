"""저장소 문서 넷이 **목적별로 갈려 있는지** 본다.

산문에는 그 짝을 보는 기계가 없어서, 한쪽을 고칠 때 나머지가 조용히 거짓이 된다.
여기서 보는 것은 내용의 정확성이 아니라 **무엇이 어느 파일에 사는가**다 —
그것이 흐려지면 같은 사실이 두 곳에 생기고, 그때부터 한쪽은 반드시 낡는다.
"""

from pathlib import Path

from tests.markdown_reader import headings as _markdown_headings
from tests.markdown_reader import section

REPO_ROOT = Path(__file__).parents[2]

# 목적이 갈린 네 파일. CLAUDE.md 는 「어떻게 일하는가」라 별도 검사가 본다.
SPLIT_DOCUMENTS = (
    "README.md",
    "PRD.md",
    "docs/schema.md",
    "docs/decision-rules.md",
)


def _read(name: str) -> str:
    return (REPO_ROOT / name).read_text(encoding="utf-8")


def test_prd_holds_scope_and_constraints() -> None:
    """PRD 는 무엇을 왜 어디까지 만드는지를 든다."""
    content = _read("PRD.md")

    # **글자가 아니라 제목으로 본다.** 포함 여부만 보면 `## 하지 않을 일` 을
    # 지워도 앞 설명과 다음 절 본문에 같은 글자가 남아 통과하고, `## 제약` 을
    # 지워도 H1 의 「범위와 제약」이 대신 맞는다. 그러면 **목적별 구조가 무너진
    # 바로 그 경우**를 이 검사가 못 잡는다.
    present = headings("PRD.md")
    for title in (
        "문제",
        "핵심 사용자와 시나리오",
        "성공 기준",
        "만드는 순서 — 0 · 1 · 2단계",
        "하지 않을 일",
        "합성 데이터 기반 데모의 한계",
        "나중에 할 일",
        "제약",
    ):
        assert title in present, title

    # 「나중에 할 일」이 드는 항목. 확장 계획이 통째로 사라지면 여기가 빨개진다.
    # **그 절 안에서 찾는다** — 문서 전체에서 찾으면 「출하 리스크」를 계획에서
    # 지워도 앞의 설명에 남은 「출하」가 대신 맞는다.
    later = section(content, "나중에 할 일")
    for planned in ("출하", "재고이동", "설비", "AI 브리핑"):
        assert planned in later, planned


def test_prd_separates_scope_ceiling_from_ordering() -> None:
    """「하지 않을 일」과 「나중에 할 일」이 섞이면 범위의 상한선이 사라진다.

    둘을 한 목록에 두면 「지금 안 함」과 「영영 안 함」이 같은 모양이 되고,
    그때부터 범위를 묻는 사람이 답을 얻지 못한다.
    """
    content = _read("PRD.md")

    # **`##` 원문이 아니라 파싱된 제목 순서로 본다.** 같은 절을 Setext 로 적으면
    # 위 검사는 통과하는데 여기만 `ValueError` 로 터지는 자리였다.
    present = headings("PRD.md")
    assert present.index("하지 않을 일") < present.index("나중에 할 일")

    # 상한선 절에 든 셋. 저자가 정한 것이라 조용히 빠지면 안 된다.
    ceiling_text = section(content, "하지 않을 일")
    for excluded in ("인증", "공개 인터넷", "합성 샘플"):
        assert excluded in ceiling_text, excluded


def test_schema_document_holds_entities_and_defers_to_code() -> None:
    """엔티티와 관계, 그리고 **왜 그 모양인지**가 여기 산다."""
    content = _read("docs/schema.md")

    for entity in ("items", "bom_components", "material_lots", "quality_inspections"):
        assert entity in content, entity

    for judgement in ("품목은 한 표입니다", "BOM은 2단 고정입니다", "유효기간 설정기간"):
        assert judgement in content, judgement

    # 진실이 어디인지 적혀 있지 않으면 이 문서가 코드보다 오래 산다.
    assert "backend/app/db/models.py" in content


def test_decision_rules_document_holds_the_calculations() -> None:
    """무엇을 보고 위험이라 하는지가 여기 산다."""
    content = _read("docs/decision-rules.md")

    for rule in (
        "납기 위험",
        "14일 안전재고",
        "LOT/FIFO",
        "창고와 가용 재고",
        "완제품 로트와 출하검사",
        "품질관리",
        "OQC",
    ):
        assert rule in content, rule


def test_no_heading_lives_in_two_documents() -> None:
    """같은 절 제목이 두 파일에 있으면 그 순간부터 한쪽이 낡기 시작한다.

    갈라 둔 것이 조용히 도로 합쳐지는 것을 막는 자리다. 내용의 중복까지는
    기계가 못 보지만, **제목의 중복은 볼 수 있다.**
    """
    seen: dict[str, str] = {}
    duplicates: list[str] = []

    for name in SPLIT_DOCUMENTS:
        for heading in headings(name):
            # **같은 파일 안의 반복은 중복이 아니다.** 이 검사가 묻는 것은
            # 「두 파일에 같은 제목이 있는가」이므로, 한 문서가 서로 다른 상위 절
            # 아래에 같은 하위 제목을 두는 것은 갈라 둔 것이 합쳐진 것이 아니다.
            if heading in seen and seen[heading] != name:
                duplicates.append(f"{heading!r}: {seen[heading]} 와 {name}")
            seen.setdefault(heading, name)

    assert not duplicates, duplicates


def headings(name: str) -> list[str]:
    """그 문서의 제목 글자만 돌려준다 — 읽는 규칙은 `markdown_reader` 가 든다."""
    return _markdown_headings(_read(name))
