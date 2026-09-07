"""기준정보 SQL 파일을 읽어 넣는다.

파일을 문장 단위로 잘라 하나씩 실행한다. 파일 전체를 한 번에 던지지 않는 이유는
드라이버마다 다중 문장 지원이 다르고, 실패했을 때 **몇 번째 문장이 터졌는지**를
알 수 있어야 사람이 고칠 수 있기 때문이다 — 이 파일은 사람이 고치는 표다.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session


MASTER_DATA_SQL = Path(__file__).resolve().parents[1] / "seed_data" / "master_data.sql"


def statements(sql: str) -> list[str]:
    """주석을 걷어내고 `;` 로 끊어 문장 목록을 만든다.

    문자열 리터럴 안의 `--` 와 `;` 를 주석·구분자로 오해하지 않도록 따옴표 상태를
    따라간다. 기준정보의 설명 칸에는 한글 문장이 들어가고, 거기에 세미콜론이
    한 번이라도 섞이면 조용히 반 토막 난 SQL 이 실행된다.
    """
    parsed: list[str] = []
    current: list[str] = []
    in_string = False
    index = 0
    while index < len(sql):
        character = sql[index]
        if in_string:
            # SQL 의 작은따옴표 탈출은 `''` 다. 두 글자를 함께 삼켜야 한다.
            if character == "'" and sql[index + 1 : index + 2] == "'":
                current.append("''")
                index += 2
                continue
            if character == "'":
                in_string = False
            current.append(character)
            index += 1
            continue
        if character == "'":
            in_string = True
            current.append(character)
            index += 1
            continue
        if sql.startswith("--", index):
            end_of_line = sql.find("\n", index)
            index = len(sql) if end_of_line == -1 else end_of_line
            continue
        if character == ";":
            parsed.append("".join(current).strip())
            current = []
            index += 1
            continue
        current.append(character)
        index += 1

    trailing = "".join(current).strip()
    if trailing:
        parsed.append(trailing)
    return [statement for statement in parsed if statement]


def load_master_data(session: Session, path: Path | None = None) -> int:
    """기준정보를 세션에 넣는다. 커밋하지 않는다 — 호출자가 트랜잭션을 쥔다.

    시드 전체가 트랜잭션 하나여야 「반쯤 채워진 데이터베이스」라는 상태가 아예
    없어지므로, 여기서 커밋하면 그 보장이 깨진다.
    """
    sql = (path or MASTER_DATA_SQL).read_text(encoding="utf-8")
    executed = 0
    for statement in statements(sql):
        session.execute(text(statement))
        executed += 1
    return executed
