"""Markdown 을 **규칙대로** 읽는 최소한의 장치.

문서 검사 둘이 같은 것을 본다 — 제목이 어느 파일에 사는지(`test_docs.py`)와
README 에서 사양 문서로 **닿는 길**이 있는지(`test_readme.py`). 둘 다 코드나 주석
안의 것을 진짜로 세면 거짓 판정이 난다. 그래서 읽는 자리를 한 곳에 둔다 — 두 벌로
두면 한쪽만 고쳐지고 그 사실이 초록 뒤에 숨는다.

**CommonMark 전부를 구현하지 않는다.** 여기 있는 것은 이 저장소의 문서가 실제로
쓰는 문법과, 리뷰에서 실제로 뚫린 구멍들이다. 무엇을 안 보는지는 각 함수가 적는다.
"""

import re

# 펜스는 **문자 · 길이 · 들여쓰기**를 함께 본다. ``` 만 보면 셋을 놓친다 —
# `~~~` 펜스, 1~3칸 들여쓴 펜스, 백틱 넷으로 연 블록 **안의** 백틱 셋.
_FENCE = re.compile(r"^(?P<indent> {0,3})(?P<fence>`{3,}|~{3,})(?P<info>.*)$")

# 닫는 해시(`## 제목 ##`)는 **앞에 공백이 있을 때만** 닫는 것이다. 공백 없이
# 붙은 해시는 제목의 일부다 — `# C#` 을 `C` 로 만들면 다른 문서의 `# C` 와
# 중복으로 잡혀 엉뚱한 곳이 빨개진다.
_ATX = re.compile(r"^ {0,3}(?P<level>#{1,6})[ \t]+(?P<text>.*?)(?:[ \t]+#+)?[ \t]*$")

# Setext 밑줄(`제목` 다음 줄의 `===` · `---`). 표 구분선(`| --- |`)은 파이프
# 때문에 여기 안 걸린다.
_SETEXT = re.compile(r"^ {0,3}(=+|-+)[ \t]*$")

# 이미지(`![대체글](경로)`)는 링크가 아니다 — 앞의 `!` 를 보고 뺀다.
_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)]+)\)")

# 코드 span 은 **같은 개수의 백틱**으로 열고 닫는다. `` ``[사양](x)`` `` 처럼
# 둘 이상으로 감싼 것을 한 쌍씩만 지우면 안쪽 링크 문법이 그대로 남는다.
_INLINE_CODE = re.compile(r"(?P<ticks>`+).+?(?P=ticks)", re.DOTALL)

_COMMENT = re.compile(r"<!--.*?-->")

_LIST_ITEM = re.compile(r"^ {0,3}(?:[-*+]|\d{1,9}[.)])[ \t]+")


def prose_lines(text: str) -> list[str]:
    """코드와 주석을 **빈 줄로 바꾼** 같은 길이의 줄 목록을 돌려준다.

    지우지 않고 빈 줄을 남기는 것은 **문단 경계가 살아 있어야** 하기 때문이다 —
    `문단` · 펜스 · `---` 를 그냥 이어 붙이면 없던 Setext 제목이 생긴다.

    코드로 보는 것은 셋이다: 펜스 블록, HTML 주석, 그리고 **4칸 이상 들여쓴
    블록**(CommonMark 의 indented code block). 마지막 것은 목록 안에서는 코드가
    아니라 이어지는 줄이므로, 목록 문맥에서는 세지 않는다.
    """
    out: list[str] = []
    open_fence: str | None = None
    in_comment = False

    for line in text.splitlines():
        if in_comment:
            # 주석이 펜스보다 먼저다 — 주석 안의 ``` 는 코드가 아니다.
            if "-->" not in line:
                out.append("")
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
            out.append("")
            continue

        fence = _FENCE.match(line)
        if fence is not None:
            open_fence = fence.group("fence")
            out.append("")
            continue

        line = _COMMENT.sub("", line)
        if "<!--" in line:
            line = line.split("<!--", 1)[0]
            in_comment = True
        out.append(line)

    for index in _indented_code(out):
        out[index] = ""
    return out


def _indented_code(lines: list[str]) -> set[int]:
    """들여쓴 코드 블록으로 읽어야 하는 줄 번호.

    블록은 **빈 줄 다음의 4칸 들여쓴 줄**에서 열리고 덜 들여쓴 줄에서 닫힌다.
    바로 앞의 내용이 목록이면 그 들여쓰기는 코드가 아니라 **이어지는 줄**이므로
    열지 않는다 — 그쪽을 코드로 지우면 멀쩡한 목록 본문이 사라진다.
    """
    marked: set[int] = set()
    in_code = False
    previous_content: str | None = None

    for index, line in enumerate(lines):
        if not line.strip():
            continue
        indented = len(line) - len(line.lstrip(" ")) >= 4
        if in_code:
            if indented:
                marked.add(index)
                continue
            in_code = False
        elif indented and index > 0 and not lines[index - 1].strip():
            in_list = previous_content is not None and (
                _LIST_ITEM.match(previous_content) is not None
                or previous_content.startswith("  ")
            )
            if not in_list:
                in_code = True
                marked.add(index)
                continue
        previous_content = line

    return marked


def headings(text: str) -> list[str]:
    """제목 글자만 순서대로 돌려준다 — ATX(`#`~`######`)와 Setext 둘 다."""
    return [heading for _, _, heading in _heading_spans(prose_lines(text))]


def section(text: str, title: str) -> str:
    """그 제목이 여는 절의 본문을 돌려준다 — **같은 깊이 이상의 다음 제목 앞까지.**

    절 안에서 찾는 것과 문서 전체에서 찾는 것은 다르다. 전체에서 글자만 찾으면
    항목이 그 절에서 사라져도 다른 절에 같은 낱말이 있어 통과한다.
    """
    lines = prose_lines(text)
    spans = _heading_spans(lines)

    for position, (index, level, heading) in enumerate(spans):
        if heading != title:
            continue
        end = len(lines)
        for next_index, next_level, _ in spans[position + 1 :]:
            if next_level <= level:
                end = next_index
                break
        return "\n".join(lines[index:end])

    raise AssertionError(f"그런 제목이 없다: {title!r}")


def _heading_spans(lines: list[str]) -> list[tuple[int, int, str]]:
    """(줄 번호, 깊이, 제목 글자). Setext 는 **문단 위에서만** 제목이다 —
    빈 줄이나 다른 제목 위의 `---` 는 수평선이므로 세지 않는다.
    """
    out: list[tuple[int, int, str]] = []

    for index, line in enumerate(lines):
        atx = _ATX.match(line)
        if atx is not None and atx.group("text").strip():
            out.append((index, len(atx.group("level")), atx.group("text").strip()))
            continue

        setext = _SETEXT.match(line) if index else None
        if setext is None:
            continue
        previous = lines[index - 1]
        if not previous.strip():
            continue
        if _ATX.match(previous) is not None or _SETEXT.match(previous) is not None:
            continue
        out.append((index - 1, 1 if setext.group(1)[0] == "=" else 2, previous.strip()))

    return out


def link_targets(text: str) -> list[str]:
    """`[보이는 글](목적지)` 의 목적지만 돌려준다.

    코드 블록 · 주석 · 코드 span 안의 것과 이미지는 뺀다 — **화면에서 눌러 갈 수
    있는 것**만이 닿을 길이기 때문이다.
    """
    out: list[str] = []
    for line in prose_lines(text):
        for target in _LINK.findall(_INLINE_CODE.sub("", line)):
            target = target.strip()
            if target:
                # `(경로 "제목")` 형태에서 경로만 든다.
                out.append(target.split()[0])
    return out
