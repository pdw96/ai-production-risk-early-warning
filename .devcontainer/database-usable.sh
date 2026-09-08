#!/usr/bin/env bash
# 「이 데이터베이스를 **지금 쓸 수 있는가**」에 답하는 단 한 곳. 쓸 수 있으면 0.
#
#   bash database-usable.sh <호스트> <포트> <데이터베이스>
#
# 서버가 살아 있는지가 아니라 **표를 만들 수 있는지**를 묻는다. 셋은 다른
# 질문이고, 앞의 것으로 뒤의 것을 대신하면 그 틈으로 결함이 지나간다.
#
#   서버가 산다 ≠ 그 데이터베이스가 있다 ≠ 이 역할이 거기에 표를 만들 수 있다
#
# 실측(2026-09-08, PostgreSQL 16.13): 없는 데이터베이스를 향해
# `pg_isready -h /var/run/postgresql -p 5432` 는 **종료코드 0**(accepting
# connections)을 냈고, 같은 자리로 `psql` 을 붙이니
# `FATAL: database "..." does not exist` 로 종료코드 2 였다. 그리고 PostgreSQL 15
# 부터 `public` 스키마의 `CREATE` 가 `PUBLIC` 에서 회수되어, 남이 만들어 둔
# 데이터베이스에는 **붙기는 되는데 표는 못 만드는** 상태가 흔하다 — 그때
# `SELECT 1` 은 `1` 을 돌려주고 `CREATE TABLE` 은 `permission denied for schema
# public` 으로 거부됐다.
#
# 바로 뒤에 오는 것이 `alembic upgrade head` 이고 그것이 하는 일이 `public`
# 스키마에 표를 만드는 것이므로, 물어야 하는 것은 그 권한이다. 이 질의는 접속도
# 함께 본다 — 못 붙으면 여기서 실패한다.
#
# **`CREATEDB` 도 함께 묻는다.** 사람이 셸에서 곧바로 치는 것은
# `python -m pytest tests` 이고, 그 안의 `test_live_engine.py` 는 일회용
# 데이터베이스를 만들어 쓴다 — `CREATE DATABASE` 다. 역할이 `public` 의
# `CREATE` 는 지녔는데 `CREATEDB` 를 잃은 상태가 있을 수 있고, 그때 이 판정이
# 표 권한만 보면 훅은 주소를 내보내고 검사는 그 자리에서 죽는다. 프로파일 훅은
# `database.sh` 를 거치지 않으므로 **권한을 되돌려 줄 길도 지나치지 않는다.**
#
# 그래서 이 파일이 답하는 것은 「붙을 수 있는가」가 아니라 **「이 저장소가 이
# 데이터베이스에 하려는 일을 다 할 수 있는가」**다. `database.sh` 는 이 판정에
# 닿기 전에 `CREATEDB` 를 채워 두므로 그쪽에서는 늘 참이고, 조건이 늘어난다고
# 고르던 것을 못 고르게 되지 않는다.
#
# 이 파일을 부르는 곳은 둘이다 — 엔진을 고르는 `database.sh`, 그리고 이미 고른
# 주소를 다시 내보낼지 정하는 `setup.sh` 의 프로파일 훅. 둘이 같은 질문에 다르게
# 답하면 준비는 PostgreSQL 을 고르고 셸은 SQLite 로 도는 일이 생긴다.
set -uo pipefail

[ "$#" -eq 3 ] || exit 2

# shellcheck source=.devcontainer/libpq.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/libpq.sh"
clear_ambient_libpq_environment

# `-w` 는 「비밀번호를 절대 묻지 말라」다. 부르는 자리 중 하나는 프로파일 훅이고,
# 거기서 물음이 뜨면 사람이 새 셸을 열 때마다 프롬프트에 걸린다.
psql -w -h "$1" -p "$2" -d "$3" -qtAc \
  "SELECT has_schema_privilege(current_user, 'public', 'USAGE')
      AND has_schema_privilege(current_user, 'public', 'CREATE')
      AND (SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname = current_user)" \
  2> /dev/null | grep -qx t
