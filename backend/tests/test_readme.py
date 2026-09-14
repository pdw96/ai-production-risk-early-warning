from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]


def test_readme_documents_local_run() -> None:
    """README 는 **돌리는 법과 보이는 것**만 든다.

    사양(범위·데이터 모델·판정 규칙)은 목적이 달라 옆 파일로 나갔다 —
    test_docs.py 가 그쪽을 본다.
    """
    content = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    required_sections = (
        "아키텍처",
        "샘플 데이터 초기화",
        "사전 요구사항",
        "백엔드 설치·실행",
        "프론트엔드 설치·실행",
        "Docker",
        "화면 안내",
        "테스트와 종단 간 검증",
        # 화면 안내가 드는 업무 모듈. 화면이 사라지면 여기가 먼저 빨개진다.
        "기준정보관리",
        "구매관리",
        "재고관리",
        "생산관리",
        "영업관리",
        "품질관리",
        "창고별 재고",
    )
    for section in required_sections:
        assert section in content, section


def test_readme_points_at_the_documents_that_hold_the_spec() -> None:
    """가리키는 줄이 없으면 나간 사양은 그냥 사라진 것이 된다.

    README 만 열어 본 사람이 범위·모델·규칙에 닿을 길이 여기다.
    """
    content = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    for target in ("PRD.md", "docs/schema.md", "docs/decision-rules.md"):
        assert target in content, target
