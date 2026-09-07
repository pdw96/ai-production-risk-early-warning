"""기준정보 SQL 파일을 읽어 넣는다.

파일을 문장 단위로 잘라 하나씩 실행한다. 파일 전체를 한 번에 던지지 않는 이유는
드라이버마다 다중 문장 지원이 다르고, 실패했을 때 **몇 번째 문장이 터졌는지**를
알 수 있어야 사람이 고칠 수 있기 때문이다 — 이 파일은 사람이 고치는 표다.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session


SEED_DATA_DIRECTORY = Path(__file__).resolve().parents[1] / "seed_data"

# 순서가 있는 목록이다. 뒤 파일이 앞 파일의 행을 코드로 찾아 참조하므로, 이
# 차례가 곧 의존 관계다. 파일을 하나로 합치지 않는 이유는 그 의존 관계를
# 파일 이름으로 읽히게 하기 위해서다.
MASTER_DATA_FILES: tuple[str, ...] = (
    "01_common_codes.sql",
    "02_purchase.sql",
)


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


def load_sql_file(session: Session, path: Path) -> int:
    """SQL 파일 하나를 문장 단위로 실행하고 실행한 문장 수를 돌려준다."""
    executed = 0
    for statement in statements(path.read_text(encoding="utf-8")):
        session.execute(text(statement))
        executed += 1
    return executed


def load_master_data(
    session: Session,
    file_names: tuple[str, ...] = MASTER_DATA_FILES,
) -> int:
    """기준정보를 세션에 넣는다. 커밋하지 않는다 — 호출자가 트랜잭션을 쥔다.

    시드 전체가 트랜잭션 하나여야 「반쯤 채워진 데이터베이스」라는 상태가 아예
    없어지므로, 여기서 커밋하면 그 보장이 깨진다.
    """
    return sum(
        load_sql_file(session, SEED_DATA_DIRECTORY / file_name)
        for file_name in file_names
    )
