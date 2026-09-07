"""마이그레이션 앞에 서는 검사 하나.

이 저장소의 이전 판은 Alembic 없이 `create_all` 로 표를 만들었다. 그런
데이터베이스에는 표가 있는데 `alembic_version` 이 없고, Alembic 은 그것을
**빈 데이터베이스**로 읽는다 — 초기 리비전을 처음부터 돌리다가 이미 있는
표에서 `table ... already exists` 로 죽는다. 진입점은 마이그레이션을 먼저
돌리므로, 기동은 그 자리에서 멈추고 시드 판단까지 가지도 못한다.

멈추는 것 자체는 옳다. 옛 데이터베이스를 말없이 지우는 쪽이 훨씬 나쁘다.
잘못된 것은 **왜 멈췄는지 알 수 없다는 것**이므로, 여기서 먼저 알아보고
사람이 고를 수 있는 두 길을 적어 준다.
"""

from __future__ import annotations

import sys

from sqlalchemy import inspect

from app.db.base import Base, LEGACY_TABLE_NAMES, engine, register_models


ALEMBIC_TABLE = "alembic_version"

MESSAGE = """\
표가 이미 있는데 Alembic 버전 표({table})가 없습니다.

Alembic 없이 만들어진 이전 판의 데이터베이스입니다. 이대로 마이그레이션을
돌리면 이미 있는 표에서 실패합니다. 두 길 중 하나를 고르십시오.

  1. 이 판의 스키마는 이전 판과 다릅니다(품목 통합 · 로트 · 기준정보).
     합성 데이터라면 지우고 다시 만드는 것이 맞습니다.
         python -m app.seed
  2. 지울 수 없는 데이터라면, 스키마가 현재 리비전과 같은지 **직접 확인한
     뒤에만** 버전을 찍으십시오. 확인 없이 찍으면 이후 마이그레이션이
     조용히 건너뛰어집니다.
         python -m alembic stamp head

발견된 표: {tables}"""


def check() -> str | None:
    """막아야 할 상태면 사람에게 보일 문장을, 아니면 None 을 돌려준다.

    보는 것은 **이 앱의 표뿐**이다. 아무 표나 있으면 막으면, 스키마를 나눠 쓰는
    곳에서는 옆에 있는 남의 표 하나 때문에 **첫 기동이 영영 마이그레이션을 하지
    못한다** — 그리고 그때 알려 주는 두 길은 둘 다 그 상태에 대한 답이 아니다.
    지우는 쪽(`drop_all`)이 이 앱의 표만 지우기로 한 것과 같은 이유이며, 같은
    목록을 본다.
    """
    register_models()
    owned = set(Base.metadata.tables) | set(LEGACY_TABLE_NAMES)

    present = sorted(set(inspect(engine).get_table_names()) & (owned | {ALEMBIC_TABLE}))
    if not present or ALEMBIC_TABLE in present:
        return None
    return MESSAGE.format(table=ALEMBIC_TABLE, tables=", ".join(present))


def main() -> None:
    problem = check()
    if problem is None:
        return
    print(problem, file=sys.stderr)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
