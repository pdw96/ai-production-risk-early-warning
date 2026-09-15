from pathlib import Path

from tests.markdown_reader import headings, link_targets, section

REPO_ROOT = Path(__file__).parents[2]


def test_readme_documents_local_run() -> None:
    """README 는 **돌리는 법과 보이는 것**만 든다.

    사양(범위·데이터 모델·판정 규칙)은 목적이 달라 옆 파일로 나갔다 —
    test_docs.py 가 그쪽을 본다.

    **여기 든 것은 성격이 둘이고, 그래서 보는 방법도 둘이다.** 한 반복문에 묶어
    글자 포함으로 보면 절 제목이 지워져도 본문·링크·표에 남은 같은 글자가 대신
    맞는다. 반대로 전부 제목으로 요구하면 **애초에 제목이 아닌 것**이 빨개진다 —
    업무 모듈 일곱은 「화면 안내」 절의 **표 행**이지 절이 아니다.
    """
    content = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    # ① 절은 제목으로 본다. `Docker` 가 아니라 `Docker로 실행` 인 것이 그 차이다 —
    #    부분 문자열로 보면 제목이 무엇인지 검사가 알지 못한다.
    present = headings(content)
    for title in (
        "아키텍처",
        "샘플 데이터 초기화",
        "사전 요구사항",
        "백엔드 설치·실행",
        "프론트엔드 설치·실행",
        "Docker로 실행",
        "화면 안내",
        "테스트와 종단 간 검증",
    ):
        assert title in present, title

    # ② 업무 모듈은 제목이 아니라 그 절의 **표 행**이다. 절로 좁히는 것만으로는
    #    모자란다 — 절을 설명하는 산문에도 같은 낱말이 있어서, 화면이 표에서
    #    사라져도 그쪽이 대신 맞는다(실제로 행을 지워 확인했다). 행만 본다.
    rows = [
        line
        for line in section(content, "화면 안내").splitlines()
        if line.lstrip().startswith("|")
    ]
    screens = "\n".join(rows)
    for module in (
        "기준정보관리",
        "구매관리",
        "재고관리",
        "생산관리",
        "영업관리",
        "품질관리",
        "창고별 재고",
    ):
        assert module in screens, module


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
