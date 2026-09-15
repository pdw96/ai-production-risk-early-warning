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


def test_indented_code_opens_where_there_is_no_paragraph_to_interrupt() -> None:
    """「빈 줄 다음」만 보면 **문서 전체를 코드로 만들어도** 첫 줄에서 안 열린다.

    그러면 뒤의 들여쓴 줄이 전부 산문으로 새서, README 를 통째로 4칸 들여써
    링크를 하나도 누를 수 없게 해 놓아도 도달성 검사가 초록이 된다.
    """
    assert link_targets("    [사양](docs/schema.md)\n    [범위](PRD.md)\n") == []
    assert link_targets("# 제목\n    [사양](docs/schema.md)\n") == []


def test_reference_links_are_a_path_too() -> None:
    """참조형도 화면에서는 똑같이 눌린다 — 안 세면 멀쩡한 정리가 CI 를 막는다."""
    assert link_targets("[사양][schema]\n\n[schema]: docs/schema.md\n") == [
        "docs/schema.md"
    ]
    assert link_targets("[schema][]\n\n[schema]: docs/schema.md\n") == ["docs/schema.md"]

    # 정의가 없으면 그냥 대괄호 글자다.
    assert link_targets("[사양][없는라벨]\n") == []


def test_raw_html_blocks_hide_their_link_syntax() -> None:
    """`<pre>` 안의 `[사양](x)` 는 글자로 찍힌다 — 눌러 갈 수 없다."""
    assert link_targets("<pre>\n[사양](docs/schema.md)\n</pre>\n") == []


def test_code_inside_a_list_is_measured_from_the_content_column() -> None:
    """목록 안의 코드는 **그 항목의 내용 열**부터다 — `- 항목` 이면 6칸.

    4칸으로 고정하면 둘이 한꺼번에 어긋난다: 4칸은 이어지는 줄인데 지우고,
    6칸은 코드인데 남긴다. 아래 둘이 그 두 자리다.
    """
    assert link_targets("- 항목\n\n      [사양](docs/schema.md)\n") == []
    assert link_targets("- 항목\n\n    [사양](docs/schema.md)\n") == ["docs/schema.md"]


def test_the_content_column_follows_the_nesting_depth() -> None:
    """중첩 목록의 내용 열은 **그 마커가 앉은 칸**에서 센다.

    최상위 규칙(`{0,3}`)으로 중첩 마커를 찾으면 못 잡고 들여쓰기+4 로 떨어져
    내용 열을 실제보다 얕게 잡는다. 그러면 **이어지는 줄이 코드로 지워져**
    멀쩡한 문서의 링크가 없는 것이 된다 — 검사를 막는 방향이라 급하다.
    """
    # `    - 항목` 은 내용 열이 6이라 코드는 10칸부터다. 8칸은 이어지는 줄이다.
    assert link_targets("- 바깥\n\n    - 항목\n\n        [사양](docs/schema.md)\n") == [
        "docs/schema.md"
    ]

    # 세 단 중첩. `        - 셋` 은 내용 열이 10이라 12칸은 이어지는 줄이고,
    # 14칸이라야 비로소 코드다.
    three = "- 하나\n\n    - 둘\n\n        - 셋\n\n{indent}[사양](docs/schema.md)\n"
    assert link_targets(three.format(indent=" " * 12)) == ["docs/schema.md"]
    assert link_targets(three.format(indent=" " * 14)) == []


def test_a_wide_marker_gap_starts_the_item_with_code() -> None:
    """마커 뒤 공백이 **5칸 이상**이면 그 항목은 들여쓴 코드로 시작한다.

    그때 내용 열은 공백 전부가 아니라 **마커 다음 한 칸**이다. 공백을 그대로
    더하면 내용 열이 깊어져 **코드 블록 안의 링크가 산문으로 새어 나온다.**
    지적은 중첩만 들었지만 뿌리가 같아 최상위도 함께 든다.
    """
    # `-     항목` 은 내용 열이 2라 코드는 6칸부터. 5칸은 아직 이어지는 줄이다.
    top = "-     항목\n\n{indent}[사양](docs/schema.md)\n"
    assert link_targets(top.format(indent=" " * 6)) == []
    assert link_targets(top.format(indent=" " * 5)) == ["docs/schema.md"]

    # 중첩하면 마커가 4칸에 앉아 내용 열이 6, 코드는 10칸부터다.
    nested = "- 바깥\n\n    -     항목\n\n{indent}[사양](docs/schema.md)\n"
    assert link_targets(nested.format(indent=" " * 10)) == []
    assert link_targets(nested.format(indent=" " * 9)) == ["docs/schema.md"]


def test_reference_labels_match_by_the_commonmark_rule() -> None:
    """속 공백을 접고 case folding 해서 맞춘다 — 글자 그대로 비교하지 않는다."""
    assert link_targets("[품목 규칙]\n\n[품목   규칙]: docs/schema.md\n") == [
        "docs/schema.md"
    ]
    assert link_targets("[Schema]\n\n[SCHEMA]: docs/schema.md\n") == ["docs/schema.md"]


def test_indented_code_opens_after_a_setext_heading_too() -> None:
    """Setext 도 제목이다 — 그 밑줄 다음 줄에서 코드가 열린다."""
    assert link_targets("제목\n=====\n    [사양](docs/schema.md)\n") == []


def test_a_definition_cannot_interrupt_a_paragraph() -> None:
    """문단에 이어 붙은 `[label]: 목적지` 는 정의가 아니라 그 문단의 글자다.

    정의로 세면 뒤의 `[label]` 이 링크가 되어, **화면에 누를 것이 없는 README**
    가 도달성 검사를 통과한다.
    """
    assert link_targets("문단\n[schema]: docs/schema.md\n\n[schema]\n") == []

    # 빈 줄 뒤의 같은 줄은 진짜 정의다 — 여기까지 막으면 멀쩡한 문서가 빨개진다.
    assert link_targets("문단\n\n[schema]: docs/schema.md\n\n[schema]\n") == [
        "docs/schema.md"
    ]


def test_angle_bracketed_destinations_are_a_path() -> None:
    """`<경로>` 는 유효하고 **눌리는** 표기다 — 꺾쇠째 읽으면 없는 경로가 된다."""
    assert link_targets("[사양](<docs/schema.md>)\n") == ["docs/schema.md"]


def test_a_backtick_fence_cannot_carry_a_backtick_info_string() -> None:
    """그 줄은 펜스를 **열지 않는다** — 열면 뒤의 진짜 제목이 코드로 지워진다."""
    assert headings("``` bad`info\n# 진짜 제목\n") == ["진짜 제목"]

    # 물결 펜스에는 그 제한이 없다.
    assert headings("~~~ bad`info\n# 숨은 제목\n~~~\n") == []


def test_an_escaped_bracket_is_not_a_link() -> None:
    """`\\[사양](x)` 는 글자 그대로 찍힌다 — 눌러 갈 수 없다."""
    assert link_targets("\\[사양](docs/schema.md)\n") == []


def test_markdown_inside_other_html_still_counts() -> None:
    """**여기가 넓히면 깨지는 자리다.** `<sub>`·`<details>` 안은 파싱된다.

    `PRD.md` 가 `<sub>` 안에 진짜 링크를 들고 있어서, 원시 HTML 을 넓게 잡으면
    멀쩡한 닿을 길이 사라진다.
    """
    assert link_targets("<sub>[사양](docs/schema.md)</sub>\n") == ["docs/schema.md"]
    assert link_targets(
        "<details>\n<summary>x</summary>\n\n[사양](docs/schema.md)\n\n</details>\n"
    ) == ["docs/schema.md"]
