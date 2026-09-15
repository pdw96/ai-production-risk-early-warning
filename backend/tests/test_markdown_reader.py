"""문서 검사 둘이 기대는 **읽는 규칙**을 자기 자리에서 고정한다.

`test_docs.py` 와 `test_readme.py` 는 저장소의 실제 문서만 본다. 그래서 읽는 쪽이
틀려도 **지금 문서가 그 입력을 안 쓰면 초록**이고, 리뷰 세 라운드가 잡은 구멍
아홉 개가 전부 그 자리였다 — 문서를 한 줄 고치는 날 비로소 빨개지는 종류다.
합성 입력은 그 날을 앞당긴다.

여기 든 것은 **닫힌 지적의 재발 방지**와, 그것을 고치다 반대쪽으로 넘어간 자리
하나다. 엔진(`DATABASE_URL`)은 이 검사의 답을 바꿀 수 없다 — 읽는 것이 글자뿐이라
데이터베이스를 아예 열지 않기 때문이고, 그래서 공용 픽스처를 받지 않는다.
"""

from tests.markdown_reader import headings, link_targets, section

# --- 펜스 --------------------------------------------------------------------


def test_fence_is_read_by_character_length_and_indent() -> None:
    """``` 만 보면 셋을 놓친다 — 그 안의 주석이 제목으로 샌다."""
    assert headings("~~~\n# 가짜\n~~~\n") == []
    assert headings("  ```\n# 가짜\n  ```\n") == []
    assert headings("````\n```\n# 가짜\n```\n````\n") == []


def test_info_string_does_not_close_a_fence() -> None:
    """```python 은 닫는 펜스가 아니다. 닫힘으로 읽으면 뒤 코드가 산문이 된다."""
    assert headings("```\n```python\n# 주석\n```\n") == []


def test_removed_fence_leaves_a_paragraph_boundary() -> None:
    """펜스를 흔적 없이 지우면 `문단` 과 `---` 가 붙어 없던 제목이 생긴다."""
    assert headings("문단\n```\ncode\n```\n---\n") == []


# --- 제목 --------------------------------------------------------------------


def test_all_six_atx_levels_count() -> None:
    """H1~H3 만 세면 문서가 세분화되는 날 중복 검사가 조용히 무력해진다."""
    assert headings("#### 넷\n##### 다섯\n###### 여섯\n") == ["넷", "다섯", "여섯"]


def test_trailing_hash_is_kept_when_it_is_part_of_the_text() -> None:
    """`# C#` 의 끝 해시는 닫는 것이 아니다 — 지우면 남의 `# C` 와 중복이 된다."""
    assert headings("# C#\n") == ["C#"]
    assert headings("## 제목 ##\n") == ["제목"]


def test_setext_headings_count() -> None:
    """화면에서 같은 제목이면 문법이 달라도 같은 제목이다."""
    assert headings("설치\n====\n\n다음\n----\n") == ["설치", "다음"]


def test_a_rule_after_a_block_is_not_a_setext_heading() -> None:
    """목록 · 인용 · 표의 행 위의 `---` 는 그 블록을 닫는 수평선이다.

    문단으로 세면 `- 항목` 이나 `| 1 | 2 |` 가 통째로 제목이 되고, 그러면
    `section()` 이 거기서 절을 끊어 **멀쩡한 문서에서 절의 항목이 사라진다.**
    """
    assert headings("- 항목\n---\n") == []
    assert headings("> 인용\n---\n") == []
    assert headings("| a |\n| --- |\n| 1 |\n---\n") == []
    assert headings("문단입니다\n---\n") == ["문단입니다"]  # 문단 위는 제목이 맞다


def test_section_is_not_cut_short_by_a_rule_inside_it() -> None:
    """위 결함이 실제로 무엇을 깨뜨리는지 — 절 안의 항목이 통째로 빠진다."""
    body = section("## 절\n\n- 항목\n---\n\n뒤엣것\n\n## 다음 절\n\n밖\n", "절")
    assert "뒤엣것" in body
    assert "밖" not in body


# --- 닿을 길 -----------------------------------------------------------------


def test_only_clickable_links_count_as_a_path() -> None:
    """눌러 갈 수 없는 것을 닿을 길로 세면 링크를 예시로 바꿔 놓아도 초록이다."""
    assert link_targets("[사양](docs/schema.md)\n") == ["docs/schema.md"]
    assert link_targets('[사양](docs/schema.md "제목")\n') == ["docs/schema.md"]

    for hidden in (
        "![사양](docs/schema.md)\n",  # 이미지
        "`[사양](docs/schema.md)`\n",  # 인라인 코드
        "``[사양](docs/schema.md)``\n",  # 백틱 둘 — 한 쌍씩 지우면 샌다
        "<!-- [사양](docs/schema.md) -->\n",  # 주석
        "<!--\n[사양](docs/schema.md)\n-->\n",  # 여러 줄 주석
        "```\n[사양](docs/schema.md)\n```\n",  # 펜스 블록
        "문단\n\n    [사양](docs/schema.md)\n",  # 들여쓴 코드 블록
    ):
        assert link_targets(hidden) == [], hidden


def test_indented_continuation_of_a_list_is_not_code() -> None:
    """목록 안의 들여쓰기는 코드가 아니라 이어지는 줄이다 — 그 링크는 눌린다."""
    assert link_targets("- 항목\n\n    [사양](docs/schema.md)\n") == ["docs/schema.md"]
