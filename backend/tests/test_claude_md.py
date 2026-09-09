"""`CLAUDE.md` 가 저장소와 어긋나지 않는지 본다.

`CLAUDE.md` 는 세션을 새로 열 때 제일 먼저 읽는 파일이라, 여기 적힌 값이
틀리면 **틀린 채로 다음 작업의 전제가 된다** — 대화 맥락은 비워도 이 파일은
남기 때문이다. 그래서 다른 파일과 짝을 이루는 값만은 산문에 맡기지 않는다.

`test_ci_workflow.py` 와 같은 취지이며, 보는 짝만 다르다.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def claude_md() -> str:
    return (REPOSITORY_ROOT / "CLAUDE.md").read_text(encoding="utf-8")


def test_claude_md_states_the_python_release_that_ci_and_the_image_use(
    claude_md: str,
) -> None:
    """판본이 세 곳에 적혀 있다 — 워크플로, 이미지, 그리고 이 안내.

    셋이 갈리면 로컬만 다른 판으로 돌게 되고, 그때 `test_golden_cases.py` 의
    완료예정일이 하루 어긋나 빨갛게 뜬다. 코드가 아니라 판본 문제인데 그것을
    알려 주는 것이 `CLAUDE.md` 뿐이므로, 이 파일이 낡으면 그 하루를 아무도
    설명하지 못한다.
    """
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

    assert f"파이썬은 {ci_release} 다" in claude_md, (
        f"CI 와 이미지는 파이썬 {ci_release} 로 도는데 CLAUDE.md 가 그렇게 적고 있지 않다"
    )
