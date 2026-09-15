"""Markdown 을 **규칙대로** 읽는 최소한의 장치.

문서 검사 둘이 같은 것을 본다 — 제목이 어느 파일에 사는지(`test_docs.py`)와
README 에서 사양 문서로 **닿는 길**이 있는지(`test_readme.py`). 둘 다 코드나 주석
안의 것을 진짜로 세면 거짓 판정이 난다. 그래서 읽는 자리를 한 곳에 둔다 — 두 벌로
두면 한쪽만 고쳐지고 그 사실이 초록 뒤에 숨는다.

**CommonMark 전부를 구현하지 않는다.** 여기 있는 것은 이 저장소의 문서가 실제로
쓰는 문법과, 리뷰에서 실제로 뚫린 구멍들이다. 무엇을 안 보는지는 각 함수가 적는다.

**선을 어디에 긋는지도 정해져 있다.** 기존 구조 안에서 조건 하나로 닫히는 것은
닫고, **줄 단위로 읽는 설계를 깨야 하거나 인라인 Markdown 을 실제로 파싱해야 하는
것은 닫지 않고 적는다.** 파서를 여기에 다시 만드는 것이 이 도구의 일이 아니기
때문이다 — 문서 검사 둘이 기대는 것은 「제목이 어느 파일에 사는가」와 「눌러 갈 길이
있는가」 두 가지뿐이다.

**적을 때는 새는 방향을 함께 적는다.** 거짓 초록(구멍이 있는데 통과)과 거짓
빨강(멀쩡한 문서가 막힘)은 급한 정도가 다르다 — 뒤엣것은 기여자를 당장 막으므로
선을 긋고 둘 성질의 것이 아니다.
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

# 이미지(`![대체글](경로)`)는 링크가 아니다 — 앞의 `!` 를 보고 뺀다. 백슬래시로
# 벗어난 `\[` 도 링크가 아니라 **글자 그대로** 찍히므로 같이 뺀다.
_LINK = re.compile(r"(?<![!\\])\[[^\]]*\]\(([^)]+)\)")

# 코드 span 은 **같은 개수의 백틱**으로 열고 닫는다. `` ``[사양](x)`` `` 처럼
# 둘 이상으로 감싼 것을 한 쌍씩만 지우면 안쪽 링크 문법이 그대로 남는다.
_INLINE_CODE = re.compile(r"(?P<ticks>`+).+?(?P=ticks)", re.DOTALL)

_COMMENT = re.compile(r"<!--.*?-->")

# **Markdown 이 아예 파싱되지 않는 원시 HTML 블록**(CommonMark 의 HTML block
# type 1)만 코드로 본다. 그 안의 `[사양](x)` 는 화면에 글자로 찍히지 링크가 되지
# 않는다. 다른 HTML(`<details>` · `<div>`)과 인라인 `<sub>` 는 **여기 넣지
# 않는다** — 그 안의 Markdown 은 실제로 파싱되고, `PRD.md` 는 `<sub>` 안에 진짜
# 링크를 들고 있다. 넣었다면 멀쩡한 닿을 길이 사라진다.
_HTML_RAW_OPEN = re.compile(
    r"^ {0,3}<(?P<tag>pre|script|style|textarea)(?:[ \t>]|/>|$)", re.IGNORECASE
)

# 참조형 링크의 정의(`[label]: 목적지`). 화면에서는 인라인 링크와 똑같이 눌린다 —
# 안 세면 **평범한 Markdown 정리가 CI 를 막는다.**
_LINK_DEFINITION = re.compile(r"^ {0,3}\[(?P<label>[^\]]+)\]:\s*(?P<target>\S+)")

# 참조형 사용(`[보이는 글][label]` · `[label][]` · `[label]`). 마지막 꼴은 **정의된
# 라벨일 때만** 링크이므로, 정의를 모은 뒤에 거른다.
_LINK_REFERENCE = re.compile(
    r"(?<![!\\])\[(?P<text>[^\]]*)\](?:\[(?P<label>[^\]]*)\])?"
)

_LIST_ITEM = re.compile(r"^ {0,3}(?:[-*+]|\d{1,9}[.)])[ \t]+")

# **내용 열을 잴 때만** 쓰는 목록 마커 — 앞 공백을 몇 칸이든 받는다. 위의 `{0,3}`
# 은 **최상위** 목록의 규칙이라 `    - 항목` 같은 중첩 마커를 못 잡고, 그러면
# `_code_column` 이 들여쓰기+4 로 떨어져 **내용 열을 실제보다 얕게** 잡는다.
# 그 자리는 `_heading_spans` 의 Setext 판정과 뜻이 다르므로 **정규식을 나눈다** —
# 거기서는 최상위 규칙이 맞고, 넓히면 깊이 들여쓴 줄까지 목록으로 읽는다.
_LIST_CONTENT = re.compile(r"^ *(?:[-*+]|\d{1,9}[.)])[ \t]+")

# Setext 밑줄은 **문단** 위에서만 제목이다. 목록 항목 · 인용 · 표의 행은 문단이
# 아니라 제 나름의 블록이고, 그 다음 줄의 `---` 는 그 블록을 닫는 수평선이다 —
# 문단으로 세면 `- 항목` 이나 `| 1 | 2 |` 가 통째로 제목이 되어, 그 자리에서
# 절이 잘린다(`section()` 이 그 제목을 절의 끝으로 읽는다).
_NOT_PARAGRAPH = re.compile(r"^ {0,3}(?:>|\|)")


def prose_lines(text: str) -> list[str]:
    """코드와 주석을 **빈 줄로 바꾼** 같은 길이의 줄 목록을 돌려준다.

    지우지 않고 빈 줄을 남기는 것은 **문단 경계가 살아 있어야** 하기 때문이다 —
    `문단` · 펜스 · `---` 를 그냥 이어 붙이면 없던 Setext 제목이 생긴다.

    코드로 보는 것은 넷이다: 펜스 블록, HTML 주석, **4칸 이상 들여쓴 블록**
    (CommonMark 의 indented code block), 그리고 **Markdown 이 파싱되지 않는 원시
    HTML 블록**(`<pre>` · `<script>` · `<style>` · `<textarea>`). 셋째는 목록
    안에서는 코드가 아니라 이어지는 줄이므로 목록 문맥에서 세지 않는다.

    **안 보는 것** — `<details>` · `<div>` 같은 나머지 HTML 블록과 인라인 `<sub>`
    는 그대로 읽는다. 그 안의 Markdown 은 실제로 파싱되기 때문이고(`PRD.md` 가
    `<sub>` 안에 진짜 링크를 든다), 그래서 **여는 태그와 닫는 태그 사이에 Markdown
    을 숨기는 다른 길은 여전히 열려 있다.**
    """
    out: list[str] = []
    open_fence: str | None = None
    open_html: re.Pattern[str] | None = None
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

        if open_html is not None:
            # type 1 블록은 **빈 줄이 아니라 닫는 태그**에서 끝난다.
            if open_html.search(line):
                open_html = None
            out.append("")
            continue

        fence = _FENCE.match(line)
        if fence is not None and _opens_fence(fence):
            open_fence = fence.group("fence")
            out.append("")
            continue

        raw = _HTML_RAW_OPEN.match(line)
        if raw is not None:
            close = re.compile(rf"</{raw.group('tag')}\s*>", re.IGNORECASE)
            if not close.search(line):
                open_html = close
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


def _opens_fence(fence: re.Match[str]) -> bool:
    """여는 펜스로 볼 수 있는가 — **백틱 펜스의 정보 문자열에는 백틱이 못 온다.**

    안 보면 ``` ``` bad`info ``` 같은 줄에서 블록이 열려, **그 뒤의 진짜 제목과
    링크가 통째로 코드로 지워진다.** 물결 펜스에는 이 제한이 없다.
    """
    return not (fence.group("fence")[0] == "`" and "`" in fence.group("info"))


def _indented_code(lines: list[str]) -> set[int]:
    """들여쓴 코드 블록으로 읽어야 하는 줄 번호.

    블록은 **문단을 끊지 못할 뿐** 어디서나 열린다 — 빈 줄 다음, **문서의 첫
    줄**, 그리고 제목처럼 문단이 아닌 블록 다음이다. 「빈 줄 다음」만 보면 문서를
    통째로 4칸 들여써 코드로 만들어도 첫 줄에서 상태가 열리지 않아 **그 뒤가 전부
    산문으로 샌다.**

    **몇 칸부터 코드인지는 자리마다 다르다** — `_code_column` 이 든다.
    """
    marked: set[int] = set()
    in_code = False
    threshold = 4
    previous_content: str | None = None

    for index, line in enumerate(lines):
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if in_code:
            if indent >= threshold:
                marked.add(index)
                continue
            in_code = False
        elif _opens_indented_code(lines, index):
            threshold = _code_column(previous_content)
            if indent >= threshold:
                in_code = True
                marked.add(index)
                continue
        previous_content = line

    return marked


def _code_column(previous_content: str | None) -> int:
    """들여쓴 코드가 시작되는 열 — **목록 안에서는 그 항목의 내용 열이 기준이다.**

    `- 항목` 의 내용은 2칸 뒤에서 시작하므로 그 목록 안의 코드 블록은 **6칸**이고,
    한 단 더 들어간 `    - 항목` 이면 내용 열이 6이라 코드는 **10칸**부터다.
    4칸으로 고정해 두면 두 가지가 한꺼번에 어긋난다 — 4칸은 코드가 아니라 목록의
    **이어지는 줄**인데 코드로 지우고(거짓 빨강), 6칸은 코드인데 「목록이니까」라는
    이유로 산문에 남긴다(거짓 초록). 앞엣것을 막으려고 목록이면 통째로 열지 않던
    자리가 뒤엣것을 들이고 있었다. **열을 세면 둘 다 맞는다.**
    """
    if previous_content is None:
        return 4
    item = _LIST_CONTENT.match(previous_content)
    if item is not None:
        return item.end() + 4
    # 이어지는 줄이 이미 들여써 있으면 그 들여쓰기가 내용 열이다.
    return len(previous_content) - len(previous_content.lstrip(" ")) + 4


def _opens_indented_code(lines: list[str], index: int) -> bool:
    """그 줄에서 들여쓴 코드 블록이 열릴 수 있는가.

    CommonMark 에서 들여쓴 코드는 **문단을 끊지 못한다.** 그것이 유일한 제약이고,
    문서의 첫 줄이나 제목 다음은 끊을 문단이 없으므로 열린다.
    """
    if index == 0:
        return True
    previous = lines[index - 1]
    if not previous.strip():
        return True
    # 제목은 문단이 아니라 제 나름의 블록이라, 바로 다음 줄에서 코드가 열린다.
    # Setext 는 그 **밑줄**이 직전 줄이므로 밑줄도 함께 본다.
    return _ATX.match(previous) is not None or _SETEXT.match(previous) is not None


def headings(text: str) -> list[str]:
    """제목 글자만 순서대로 돌려준다 — ATX(`#`~`######`)와 Setext 둘 다.

    **돌려주는 것은 원문 글자이지 렌더링된 글자가 아니다.** 그래서 `## **설치**` 와
    `## 설치` 는 화면에서 같은 제목인데 다른 것으로 세어진다 — 서식만 달리하면 같은
    절을 두 문서에 둘 수 있다(**거짓 초록**). 벗기려면 강조 · 코드 · 링크를 실제로
    파싱해야 하고, 그것은 줄을 보고 제목 글자를 드는 이 도구의 범위 밖이다.
    """
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
    빈 줄 · 다른 제목 · 목록 · 인용 · 표의 행 위의 `---` 는 수평선이므로 세지
    않는다.

    **문단인지는 그 줄 하나로만 본다.** 인용 안에서 `> 문단` 다음 줄에 `> ---` 로
    적은 제목은 여기서 잡히지 않는다 — 이 저장소의 문서가 아직 그렇게 쓰지 않아서
    두는 공백이고, 쓰게 되면 그 제목이 조용히 빠진다.
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
        if _NOT_PARAGRAPH.match(previous) is not None or _LIST_ITEM.match(previous):
            continue
        out.append((index - 1, 1 if setext.group(1)[0] == "=" else 2, previous.strip()))

    return out


def link_targets(text: str) -> list[str]:
    """`[보이는 글](목적지)` 의 목적지만 돌려준다.

    코드 블록 · 주석 · 코드 span 안의 것과 이미지는 뺀다 — **화면에서 눌러 갈 수
    있는 것**만이 닿을 길이기 때문이다.

    **참조형(`[사양][schema]` 와 `[schema]: docs/schema.md`)도 센다.** 화면에서
    인라인 링크와 똑같이 눌리므로, 안 세면 평범한 Markdown 정리가 CI 를 막는다.
    `[label]` 한 꼴만 쓴 것은 **정의된 라벨일 때만** 링크다 — 정의가 없으면 그냥
    대괄호 글자이므로 세지 않는다.

    **안 보는 것 — 여러 줄에 걸친 코드 span.** `` `예시 ``…줄바꿈…`` 끝` `` 안에
    넣은 링크는 화면에서 눌리지 않는데 여기서는 세어진다(**거짓 초록**). 코드 span
    을 줄마다 지우기 때문이고, 고치려면 문서를 통째로 이어 붙여 지워야 한다.
    그러면 **짝이 맞지 않는 백틱 하나가 그 뒤의 진짜 링크까지 먹어 멀쩡한 문서를
    막는다**(거짓 빨강). 거짓 초록 하나를 닫자고 거짓 빨강을 들이지 않는다.
    """
    lines = [_INLINE_CODE.sub("", line) for line in prose_lines(text)]

    # **참조 정의는 문단을 끊지 못한다.** 문단에 바로 이어 붙은
    # `[label]: 목적지` 는 정의가 아니라 그 문단의 이어지는 글자이고, 화면에는
    # 정의도 링크도 아닌 평범한 글자로 찍힌다. 그것을 정의로 세면 뒤의
    # `[label]` 이 링크가 되어, **진짜 링크가 없는 README 가 통과한다.**
    definitions: dict[str, str] = {}
    defined_at: set[int] = set()
    for index, line in enumerate(lines):
        found = _LINK_DEFINITION.match(line)
        if found is None or not _defines_here(lines, index):
            continue
        defined_at.add(index)
        definitions.setdefault(
            _normalize_label(found.group("label")), _destination(found.group("target"))
        )

    out: list[str] = []
    for index, line in enumerate(lines):
        if index in defined_at:
            # 정의 줄 자체는 사용이 아니다 — 세면 `[label]` 을 링크로 두 번 센다.
            continue
        for raw in _LINK.findall(line):
            target = _destination(raw)
            if target:
                out.append(target)
        for found in _LINK_REFERENCE.finditer(_LINK.sub("", line)):
            label = found.group("label") or found.group("text")
            target = definitions.get(_normalize_label(label))
            if target:
                out.append(target)
    return out


def _normalize_label(label: str) -> str:
    """참조 라벨을 맞추는 규칙 — **속 공백을 접고 case folding 한다.**

    `[품목 규칙]` 과 `[품목   규칙]:` 은 CommonMark 에서 같은 라벨이다. 글자 그대로
    비교하면 정의를 못 찾아 **화면에서는 눌리는 링크가 없는 것으로 세어진다** —
    닿을 길이 멀쩡한데 검사가 막는 쪽이라 급하다.
    """
    return " ".join(label.split()).casefold()


def _defines_here(lines: list[str], index: int) -> bool:
    """그 줄이 참조 **정의**인가 — 문단에 이어 붙은 것은 정의가 아니다."""
    if index == 0:
        return True
    previous = lines[index - 1]
    if not previous.strip():
        return True
    # 제목 다음과 정의가 잇따르는 자리에서는 끊을 문단이 없다.
    return (
        _ATX.match(previous) is not None
        or _SETEXT.match(previous) is not None
        or _LINK_DEFINITION.match(previous) is not None
    )


def _destination(raw: str) -> str:
    """목적지 한 칸만 든다 — `(경로 "제목")` 에서 경로만, `<경로>` 는 꺾쇠를 벗겨서.

    꺾쇠는 유효하고 **눌리는** 표기다. 그대로 두면 `<docs/schema.md>` 라는 없는
    경로가 되어, 멀쩡한 표기 변경이 CI 를 막는다.
    """
    raw = raw.strip()
    if raw.startswith("<"):
        end = raw.find(">")
        if end != -1:
            return raw[1:end].strip()
    parts = raw.split()
    return parts[0] if parts else ""
