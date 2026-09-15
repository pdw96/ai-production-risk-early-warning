"""Markdown 을 **규칙대로** 읽는 최소한의 장치.

문서 검사 둘이 같은 것을 본다 — 제목이 어느 파일에 사는지(`test_docs.py`)와
README 에서 사양 문서로 **닿는 길**이 있는지(`test_readme.py`). 둘 다 코드 블록이나
주석 안의 것을 진짜로 세면 거짓 판정이 난다. 그래서 펜스를 읽는 자리를 한 곳에
둔다 — 두 벌로 두면 한쪽만 고쳐지고 그 사실이 초록 뒤에 숨는다.

**CommonMark 전부를 구현하지 않는다.** 여기 있는 것은 이 저장소의 문서가 실제로
쓰는 문법과, 리뷰에서 실제로 뚫린 구멍들이다. 무엇을 안 보는지는 각 함수가 적는다.
"""

import re

# 펜스는 **문자 · 길이 · 들여쓰기**를 함께 본다. ``` 만 보면 셋을 놓친다 —
# `~~~` 펜스, 1~3칸 들여쓴 펜스, 백틱 넷으로 연 블록 **안의** 백틱 셋.
_FENCE = re.compile(r"^(?P<indent> {0,3})(?P<fence>`{3,}|~{3,})(?P<info>.*)$")

_ATX = re.compile(r"^ {0,3}(?P<level>#{1,6}) +(?P<text>.+?)\s*#*\s*$")

# Setext 밑줄(`제목` 다음 줄의 `===` · `---`). 표 구분선(`| --- |`)은 파이프
# 때문에 여기 안 걸린다.
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")

# 이미지(`![대체글](경로)`)는 링크가 아니다 — 앞의 `!` 를 보고 뺀다.
_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")

_INLINE_CODE = re.compile(r"`[^`]*`")
_COMMENT = re.compile(r"<!--.*?-->")


def prose_lines(text: str) -> list[str]:
    """코드 펜스와 HTML 주석 **밖**의 줄만 돌려준다.

    펜스 안을 세면 코드의 `# 주석`이 문서 제목이 되고, 주석 안을 세면 **화면에
    안 보이는 것**이 닿을 길로 계산된다.
    """
    out: list[str] = []
    open_fence: str | None = None
    in_comment = False

    for line in text.splitlines():
        if in_comment:
            # 주석이 펜스보다 먼저다 — 주석 안의 ``` 는 코드가 아니다.
            if "-->" not in line:
                continue
            line = line.split("-->", 1)[1]
            in_comment = False

        if open_fence is not None:
            fence = _FENCE.match(line)
            if fence is not None:
                marker = fence.group("fence")
                # 닫는 펜스는 같은 문자 · 연 것 이상의 길이 · **정보 문자열이
                # 없어야** 한다. ```python 은 닫는 펜스가 아니다 — 그것을 닫힘으로
                # 읽으면 그 뒤 코드가 통째로 산문으로 샌다.
                if (
                    marker[0] == open_fence[0]
                    and len(marker) >= len(open_fence)
                    and not fence.group("info").strip()
                ):
                    open_fence = None
            continue

        fence = _FENCE.match(line)
        if fence is not None:
            open_fence = fence.group("fence")
            continue

        line = _COMMENT.sub("", line)
        if "<!--" in line:
            line = line.split("<!--", 1)[0]
            in_comment = True
        out.append(line)

    return out


def headings(text: str) -> list[str]:
    """제목 글자만 순서대로 돌려준다 — ATX(`#`~`######`)와 Setext 둘 다.

    Setext 는 **문단 위에서만** 제목이다. 빈 줄이나 다른 제목 위의 `---` 는
    수평선이므로 세지 않는다.
    """
    lines = prose_lines(text)
    out: list[str] = []

    for index, line in enumerate(lines):
        atx = _ATX.match(line)
        if atx is not None:
            out.append(atx.group("text").strip())
            continue

        if index == 0 or _SETEXT.match(line) is None:
            continue
        previous = lines[index - 1]
        if not previous.strip():
            continue
        if _ATX.match(previous) is not None or _SETEXT.match(previous) is not None:
            continue
        out.append(previous.strip())

    return out


def link_targets(text: str) -> list[str]:
    """`[보이는 글](목적지)` 의 목적지만 돌려준다.

    코드 블록 · 주석 · 인라인 코드 안의 것과 이미지는 뺀다 — **화면에서 눌러
    갈 수 있는 것**만이 닿을 길이기 때문이다.
    """
    out: list[str] = []
    for line in prose_lines(text):
        for target in _LINK.findall(_INLINE_CODE.sub("", line)):
            target = target.strip()
            if target:
                # `(경로 "제목")` 형태에서 경로만 든다.
                out.append(target.split()[0])
    return out
