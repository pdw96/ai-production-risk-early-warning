"""이 앱이 쓰는 표 이름을 한 줄에 하나씩 적는다.

`.devcontainer/app-tables.txt` 를 만드는 자리다. 셸 쪽 판정
(`database-usable.sh`)이 「이미 서 있는 표를 이 역할이 만질 수 있는가」를 물을 때
그 목록이 필요한데, 새 셸마다 파이썬을 띄우는 값(실측 0.7초)을 치를 수 없어
값만 미리 꺼내 둔다.

**목록의 출처는 `preflight.py` 와 같다.** 둘이 다른 목록을 보면 한쪽은 쓸 수
있다고 하고 다른 쪽은 막는 상태가 생긴다 — 그 둘은 같은 질문이다.

`alembic_version` 을 함께 넣는 이유는 `alembic upgrade head` 가 그 표를 직접
쓰기 때문이다. 남이 소유하고 있으면 마이그레이션은 그 자리에서 죽는다.
"""

from __future__ import annotations

from app.db.base import Base, LEGACY_TABLE_NAMES, register_models


ALEMBIC_TABLE = "alembic_version"


def table_names() -> list[str]:
    register_models()
    return sorted(set(Base.metadata.tables) | set(LEGACY_TABLE_NAMES) | {ALEMBIC_TABLE})


def main() -> None:
    for name in table_names():
        print(name)


if __name__ == "__main__":
    main()
