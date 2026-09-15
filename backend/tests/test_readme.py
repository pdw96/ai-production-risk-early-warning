from pathlib import Path

from tests.markdown_reader import link_targets

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

    README 만 열어 본 사람이 범위·모델·규칙에 닿을 길이 여기다. **문자열이 아니라
    링크를 본다** — 이름이 본문 어딘가에 적혀 있기만 하면 통과하게 두면, 링크를
    평문으로 바꾸거나 목적지를 `missing/docs/schema.md` 로 잘못 적어도 초록이다.
    그러면 이 검사가 지키려던 「닿을 길」이 없는데도 통과한다.

    **누를 수 있는 링크만 센다.** 코드 블록 · 주석 · 인라인 코드 안의 링크와
    이미지는 화면에서 눌러 갈 수 없으므로 닿을 길이 아니다 — 그것까지 세면 실제
    링크를 코드 예시로 바꿔 놓아도 초록이 된다(읽는 규칙은 `markdown_reader`).
    """
    readme = REPO_ROOT / "README.md"
    content = readme.read_text(encoding="utf-8")

    # 앵커(`#…`)는 떼고 상대 경로를 푼다.
    linked: set[str] = set()
    for target in link_targets(content):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        path = (readme.parent / target.split("#", 1)[0]).resolve()
        linked.add(str(path))

    for target in ("PRD.md", "docs/schema.md", "docs/decision-rules.md"):
        wanted = (REPO_ROOT / target).resolve()
        assert str(wanted) in linked, f"{target} 로 가는 링크가 없다"
        assert wanted.exists(), f"{target} 로 링크는 있는데 그 파일이 없다"
