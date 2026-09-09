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
# **이미 서 있는 표도 함께 묻는다.** 스키마 권한은 「새 표를 만들 수 있는가」이지
# 「남이 만들어 둔 표를 만질 수 있는가」가 아니다. 여러 사람이 쓰는 개발 호스트에서
# `production_risk` 를 먼저 만든 사람이 있으면 표의 소유자는 그 사람이고, 이쪽은
# `public` 의 `CREATE` 를 받아도 그 표에는 아무 권한이 없다.
#
# 실측(2026-09-09, PostgreSQL 16.13): `otherdev` 가 소유한 `items` 가 있는
# 데이터베이스에 `devprobe` 로 붙으니 이 판정은 **종료코드 0**(쓸 수 있다)이었고,
# 바로 다음 두 동작은 `permission denied for table items` 와
# `must be owner of table items` 로 거부됐다. 앞의 것은 `app.db.preflight` 와
# 시드가 하는 일이고, 뒤의 것은 `alembic upgrade head` 가 하는 일이다.
#
# 그래서 소유 역할을 이 역할이 지니는지 묻는다 — `pg_has_role(..., 'USAGE')` 는
# 자기 자신, 물려받은 구성원 자격, 슈퍼유저를 모두 참으로 본다. 실측:
# `GRANT otherdev TO devprobe` 뒤에는 판정이 `t` 로 바뀌었고 그때 `ALTER TABLE` 도
# 실제로 통과했으며, 되돌리자 다시 `f` 였다. 능력과 판정이 한 칸도 어긋나지 않는다.
#
# **묻는 대상은 이 앱의 표뿐이다.** 한때 `public` 의 모든 관계를 물었는데, 그것은
# 이 저장소가 이미 내린 결정과 어긋난다 — `preflight.py` 는 「보는 것은 이 앱의
# 표뿐이다. 아무 표나 있으면 막으면, 스키마를 나눠 쓰는 곳에서는 옆에 있는 남의
# 표 하나 때문에 첫 기동이 영영 마이그레이션을 하지 못한다」고 적어 두었고,
# `drop_all` 도 같은 목록을 본다. 실측(2026-09-09): 앱의 표는 전부 이 역할 소유인
# 데이터베이스에 관리자 소유 `audit_log` 하나를 두니, 앱은 `SELECT`·`ALTER` 를
# 멀쩡히 해내는데 판정만 **1**(SQLite 로 물러남)이었다.
#
# **표가 기대는 시퀀스도 함께 본다.** 생성 ID 한 줄을 넣는 데 필요한 것은 표 권한만이
# 아니다 — 기본값이 부르는 시퀀스에 `USAGE` 가 없으면 그 자리에서 죽는다.
#
# 실측(2026-09-09). 이 앱이 만드는 시퀀스는 표에 **묶여** 있어(`OWNED BY`)
# PostgreSQL 이 소유자 분리를 아예 거부한다:
# `ERROR: cannot change owner of sequence "items_id_seq" — Sequence is linked to
# table "items"`. 그래서 그 형태로는 이 틈이 생기지 않는다.
#
# 그런데 **묶이지 않은 시퀀스**는 다르다. `CREATE SEQUENCE loose_seq` 를 남이
# 소유하고 표는 `DEFAULT nextval('loose_seq')` 로 그것을 부르게 두니, 판정은
# 종료코드 **0**(쓸 수 있다)이었고 바로 다음 `INSERT` 는
# `permission denied for sequence loose_seq` 였다. 복구했거나 손으로 고친
# 데이터베이스에서 나올 수 있는 모양이다.
#
# 그래서 「이 앱의 표가 기본값으로 부르는 시퀀스」를 `pg_attrdef` 의존으로 찾아
# 함께 묻는다 — 이름으로 짐작하지 않는다.
#
# 목록은 `app-tables.txt` 에서 온다. 그 파일은 `app.db.table_names` 가 만들고
# `preflight.py` 와 같은 출처(`Base.metadata` · `LEGACY_TABLE_NAMES`)를 쓰며,
# 낡으면 검사가 빨갛다. 파이썬을 여기서 띄우지 않는 이유는 이 판정을 프로파일
# 훅이 새 셸마다 부르기 때문이다 — 실측 0.7초가 셸마다 붙는다.
#
# 그래서 이 파일이 답하는 것은 「붙을 수 있는가」가 아니라 **「이 저장소가 이
# 데이터베이스에 하려는 일을 다 할 수 있는가」**다. `database.sh` 는 이 판정에
# 닿기 전에 `CREATEDB` 를 채워 두므로 그쪽에서는 늘 참이고, 조건이 늘어난다고
# 고르던 것을 못 고르게 되지 않는다 — 새로 만든 데이터베이스에는 남의 표가 없다.
#
# 이 파일을 부르는 곳은 둘이다 — 엔진을 고르는 `database.sh`, 그리고 이미 고른
# 주소를 다시 내보낼지 정하는 `setup.sh` 의 프로파일 훅. 둘이 같은 질문에 다르게
# 답하면 준비는 PostgreSQL 을 고르고 셸은 SQLite 로 도는 일이 생긴다.
set -uo pipefail

[ "$#" -eq 3 ] || exit 2

DEVCONTAINER_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# shellcheck source=.devcontainer/libpq.sh
. "$DEVCONTAINER_DIRECTORY/libpq.sh"
clear_ambient_libpq_environment

# 목록을 SQL 배열로 옮긴다. 이름은 소문자·숫자·밑줄뿐임을 여기서 **거른다** —
# 그 파일은 자동 생성물이지만, 질의에 끼워 넣는 값을 믿지 않는 것이 맞다.
app_tables="$(sed 's/#.*//' "$DEVCONTAINER_DIRECTORY/app-tables.txt" 2> /dev/null \
  | grep -xE '[a-z][a-z0-9_]*' \
  | sed "s/.*/'&'/" | paste -sd, -)"

# 목록이 비면 물을 것이 없다. 그때 앞의 세 조건만으로 답하는 것이 맞다 — 빈
# 목록으로 `= ANY (ARRAY[])` 를 만들면 SQL 이 깨져 **모든 데이터베이스가 못 쓰는
# 것이 된다.**
[ -n "$app_tables" ] || app_tables="''"

# `-w` 는 「비밀번호를 절대 묻지 말라」다. 부르는 자리 중 하나는 프로파일 훅이고,
# 거기서 물음이 뜨면 사람이 새 셸을 열 때마다 프롬프트에 걸린다.
psql -w -h "$1" -p "$2" -d "$3" -qtAc \
  "SELECT has_schema_privilege(current_user, 'public', 'USAGE')
      AND has_schema_privilege(current_user, 'public', 'CREATE')
      AND (SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname = current_user)
      AND NOT EXISTS (SELECT 1
                        FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                       WHERE n.nspname = 'public'
                         AND NOT pg_has_role(current_user, c.relowner, 'USAGE')
                         AND ((c.relkind IN ('r', 'p', 'v', 'm', 'f')
                               AND c.relname = ANY (ARRAY[${app_tables}]))
                           OR (c.relkind = 'S'
                               AND c.oid IN (SELECT d.refobjid
                                               FROM pg_depend d
                                               JOIN pg_attrdef a ON a.oid = d.objid
                                               JOIN pg_class t ON t.oid = a.adrelid
                                               JOIN pg_namespace tn ON tn.oid = t.relnamespace
                                              WHERE d.classid = 'pg_attrdef'::regclass
                                                AND d.refclassid = 'pg_class'::regclass
                                                AND tn.nspname = 'public'
                                                AND t.relname = ANY (ARRAY[${app_tables}])))))" \
  2> /dev/null | grep -qx t
