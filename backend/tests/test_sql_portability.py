"""기준정보 SQL 이 한 엔진에서만 도는 문법을 쓰지 않는지 지킨다.

SQLite 는 숫자 칸에 글자를 넣어도 그냥 받고 불리언 칸에 `1` 을 넣어도 받는다.
PostgreSQL 은 거부한다 — 그것이 엔진을 옮긴 이유 중 하나이고, 옮기고 나서
**실제로 걸린 것**이 이 파일이 지키는 자리다.

목록을 손으로 적지 않고 모델 메타데이터에서 뽑는다. 손으로 적으면 나중에 불리언
칸이 하나 늘 때 이 검사만 조용히 뒤처진다.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import Boolean

from app.db.base import Base, register_models
from app.db.master_data_loader import MASTER_DATA_FILES, SEED_DATA_DIRECTORY, statements


ACCEPTED_BOOLEAN_LITERALS = {"TRUE", "FALSE", "NULL"}


def _split_top_level(body: str) -> list[str]:
    """괄호와 문자열 밖의 쉼표로만 자른다."""
    parts: list[str] = []
    current: list[str] = []
    in_string = False
    depth = 0
    index = 0
    while index < len(body):
        character = body[index]
        if in_string:
            if character == "'" and body[index + 1 : index + 2] == "'":
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
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            index += 1
            continue
        current.append(character)
        index += 1
    parts.append("".join(current).strip())
    return parts


def _boolean_columns(table_name: str) -> set[str]:
    register_models()
    table = Base.metadata.tables[table_name]
    return {
        column.name
        for column in table.columns
        if isinstance(column.type, Boolean)
    }


def _insert_statements() -> list[str]:
    parsed: list[str] = []
    for file_name in MASTER_DATA_FILES:
        sql = (SEED_DATA_DIRECTORY / file_name).read_text(encoding="utf-8")
        parsed.extend(
            statement
            for statement in statements(sql)
            if statement.upper().startswith("INSERT INTO")
        )
    return parsed


def test_the_master_data_files_only_insert_into_tables_that_exist() -> None:
    register_models()
    for statement in _insert_statements():
        table_name = re.match(r"INSERT INTO (\w+)", statement).group(1)
        assert table_name in Base.metadata.tables


@pytest.mark.parametrize("statement", _insert_statements())
def test_boolean_columns_are_written_as_keywords_not_as_ones_and_zeroes(
    statement: str,
) -> None:
    """PostgreSQL 은 불리언 칸에 정수를 넣으면 거부한다.

    SQLite 만 보고 개발하면 이것이 기동할 때까지 드러나지 않는다 — 그리고 그때
    실패하는 것은 시드 전체다.
    """
    header = re.match(r"INSERT INTO (\w+)\s*\(([^)]*)\)", statement)
    if header is None:
        # 컬럼 목록 없이 SELECT 로 넣는 문장은 값이 리터럴이 아니다.
        return
    table_name, column_list = header.group(1), header.group(2)
    columns = [name.strip() for name in column_list.split(",")]
    boolean_positions = [
        index
        for index, name in enumerate(columns)
        if name in _boolean_columns(table_name)
    ]
    if not boolean_positions:
        return

    values_part = statement[header.end() :]
    for row in re.findall(r"\(([^()]*(?:\([^()]*\)[^()]*)*)\)", values_part):
        cells = _split_top_level(row)
        if len(cells) != len(columns):
            continue
        for position in boolean_positions:
            assert cells[position].upper() in ACCEPTED_BOOLEAN_LITERALS, (
                f"{table_name}.{columns[position]} 에 {cells[position]} 가 들어 있다 —"
                " PostgreSQL 은 불리언 칸의 정수를 거부한다"
            )
