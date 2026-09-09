"""진입 문서 둘이 파이썬 판을 두고 갈리지 않는지 본다.

저장소에 들어오는 사람이 처음 읽는 문서는 둘이다 — 사람은 `README.md` 의
사전 요구사항을, 에이전트는 `CLAUDE.md` 를 읽는다. 여기 적힌 판이 CI·컨테이너와
다르면 **틀린 채로 다음 작업의 전제가 된다**: 3.11 환경을 만든 사람은
`test_golden_cases.py` 의 완료예정일이 하루 어긋나는 것을 보고 코드를 의심하게
되고, 그것이 판본 문제라고 알려 줄 수 있는 것은 이 두 문서뿐이다.

그래서 네 곳(워크플로 · 이미지 · `CLAUDE.md` · `README.md`)의 짝을 산문에
맡기지 않는다. `test_ci_workflow.py` 와 같은 취지이며, 보는 짝만 다르다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def python_release() -> str:
    """CI 가 검증하고 이미지가 배포하는 파이썬 판. 둘이 다르면 그 자리에서 멈춘다."""
    workflow = yaml.safe_load(
        (REPOSITORY_ROOT / ".github/workflows/cloud-validation.yml").read_text(
            encoding="utf-8"
        )
    )
    ci_releases = {
        str(step["with"]["python-version"])
        for step in workflow["jobs"]["validate"]["steps"]
        if str(step.get("uses", "")).startswith("actions/setup-python")
    }
    assert len(ci_releases) == 1, f"CI 가 파이썬 판을 여럿 쓴다: {ci_releases}"
    (ci_release,) = ci_releases

    dockerfile = (REPOSITORY_ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
    image_releases = set(re.findall(r"^FROM python:(\d+\.\d+)", dockerfile, re.M))
    assert image_releases == {ci_release}, (
        f"이미지({image_releases})와 CI({ci_release}) 의 파이썬 판이 다르다"
    )
    return ci_release


def test_claude_md_states_the_release_that_ci_and_the_image_use(
    python_release: str,
) -> None:
    guide = (REPOSITORY_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert f"파이썬은 {python_release} 다" in guide, (
        f"CI 와 이미지는 파이썬 {python_release} 로 도는데 CLAUDE.md 가 그렇게 적고 있지 않다"
    )


def test_the_readme_prerequisite_names_the_same_release(python_release: str) -> None:
    """README 는 「이상」으로 열어 두지 않는다.

    범위로 적으면 그 범위의 아무 판이나 골라도 된다는 뜻이 되는데, 실제로는
    아래 판에서 골든 케이스가 깨진다. 열어 둘 수 없는 것을 열어 둔 것처럼
    적지 않는다.
    """
    readme = (REPOSITORY_ROOT / "README.md").read_text(encoding="utf-8")
    stated = re.search(r"^- Python (\d+\.\d+)(.*)$", readme, re.M)
    assert stated, "README 의 사전 요구사항에서 Python 줄을 찾지 못했다"

    assert stated.group(1) == python_release, (
        f"README 는 파이썬 {stated.group(1)}, CI 와 이미지는 {python_release} 다"
    )
    assert "이상" not in stated.group(2), (
        f"README 가 파이썬 판을 범위로 적고 있다: {stated.group(0)!r}"
    )
