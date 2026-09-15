"""저장소 문서 넷이 **목적별로 갈려 있는지** 본다.

산문에는 그 짝을 보는 기계가 없어서, 한쪽을 고칠 때 나머지가 조용히 거짓이 된다.
여기서 보는 것은 내용의 정확성이 아니라 **무엇이 어느 파일에 사는가**다 —
그것이 흐려지면 같은 사실이 두 곳에 생기고, 그때부터 한쪽은 반드시 낡는다.
"""

import re
from pathlib import Path

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

    for section in (
        "## 문제",
        "핵심 사용자와 시나리오",
        "성공 기준",
        "만드는 순서",
        "하지 않을 일",
        "나중에 할 일",
        "합성 데이터 기반 데모",
        "제약",
    ):
        assert section in content, section

    # 「나중에 할 일」이 드는 항목. 확장 계획이 통째로 사라지면 여기가 빨개진다.
    for planned in ("출하", "재고이동", "설비", "AI 브리핑"):
        assert planned in content, planned


def test_prd_separates_scope_ceiling_from_ordering() -> None:
    """「하지 않을 일」과 「나중에 할 일」이 섞이면 범위의 상한선이 사라진다.

    둘을 한 목록에 두면 「지금 안 함」과 「영영 안 함」이 같은 모양이 되고,
    그때부터 범위를 묻는 사람이 답을 얻지 못한다.
    """
    content = _read("PRD.md")

    ceiling = content.index("## 하지 않을 일")
    ordering = content.index("## 나중에 할 일")
    assert ceiling < ordering

    # 상한선 절에 든 셋. 저자가 정한 것이라 조용히 빠지면 안 된다.
    ceiling_text = content[ceiling:ordering]
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
        for heading in _headings(name):
            # **같은 파일 안의 반복은 중복이 아니다.** 이 검사가 묻는 것은
            # 「두 파일에 같은 제목이 있는가」이므로, 한 문서가 서로 다른 상위 절
            # 아래에 같은 하위 제목을 두는 것은 갈라 둔 것이 합쳐진 것이 아니다.
            if heading in seen and seen[heading] != name:
                duplicates.append(f"{heading!r}: {seen[heading]} 와 {name}")
            seen.setdefault(heading, name)

    assert not duplicates, duplicates


# 펜스는 **문자와 길이와 들여쓰기**를 함께 본다. ``` 만 보면 세 가지를 놓친다 —
# `~~~` 펜스, 1~3칸 들여쓴 펜스, 그리고 백틱 넷으로 연 블록 **안의** 백틱 셋이다.
# 마지막 것은 닫는 펜스가 아닌데 상태를 뒤집어, 코드 안의 `# 백엔드` 를 제목으로
# 세게 만든다.
_FENCE = re.compile(r"^(?P<indent> {0,3})(?P<fence>`{3,}|~{3,})")

# 제목은 **H1~H6 전부**다. H3 까지만 보면 문서가 잘게 갈릴 때 `####` 이하의
# 중복이 조용히 통과하고, 그 순간 이 검사가 막으려던 것이 무력해진다.
_HEADING = re.compile(r"^ {0,3}(?P<level>#{1,6}) +(?P<text>.+?)\s*#*\s*$")


def _headings(name: str) -> list[str]:
    """코드 블록 밖의 Markdown 제목만 돌려준다."""
    out: list[str] = []
    open_fence: str | None = None

    for line in _read(name).splitlines():
        fence = _FENCE.match(line)
        if fence is not None:
            marker = fence.group("fence")
            if open_fence is None:
                open_fence = marker
                continue
            # 닫는 펜스는 **같은 문자**이고 **연 것보다 짧지 않아야** 한다.
            if marker[0] == open_fence[0] and len(marker) >= len(open_fence):
                open_fence = None
            continue
        if open_fence is not None:
            continue
        match = _HEADING.match(line)
        if match is not None:
            out.append(match.group("text").strip())
    return out
