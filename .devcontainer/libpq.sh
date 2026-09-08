#!/usr/bin/env bash
# 환경에 내보내져 있는 libpq 변수를 지운다. **목록이 적히는 단 한 곳.**
#
# `psql` · `createdb` · `pg_isready` 는 모두 `PGHOST` · `PGPORT` · `PGDATABASE`
# 같은 변수를 읽는다. 개발자의 셸에 그런 것이 하나라도 있으면 조사와 생성은
# 그쪽 클러스터로 가는데, 우리가 내미는 주소는 소켓과 포트로 고정되어 있다.
# 그러면 만든 곳과 알려 준 곳이 갈린다.
#
# 실측(2026-09-08): 같은 호스트에 16/alt(5433)를 띄우고 `PGPORT=5433` 을 내보낸
# 채 `database.sh` 를 돌리면 `production_risk` 는 5433 에 생기는데 돌려주는
# 주소는 포트가 없어 5432 를 가리켰다.
#
# 목적지를 정하는 `PGHOST` · `PGPORT` 는 **여기서 지우기만** 한다. 무엇으로
# 정할지는 이 파일을 읽는 쪽이 안다.
clear_ambient_libpq_environment() {
  unset PGHOST PGHOSTADDR PGPORT PGUSER PGDATABASE PGSERVICE PGSERVICEFILE \
    PGPASSFILE PGPASSWORD PGOPTIONS PGSSLMODE PGREQUIRESSL PGCHANNELBINDING \
    PGTARGETSESSIONATTRS PGCLIENTENCODING PGCONNECT_TIMEOUT
}
