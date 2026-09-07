"""Alembic 실행 환경.

접속 주소를 alembic.ini 에 적지 않고 앱 설정에서 읽는다. 두 곳에 적으면
마이그레이션이 앱과 **다른 데이터베이스**를 고치는 사고가 난다 — 그때 화면은
멀쩡하고 표만 조용히 어긋난다.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import DATABASE_URL
from app.db.base import Base, register_models


config = context.config

# 부르는 쪽이 주소를 정해 두었으면 그것을 따른다. 앱 설정을 무조건 덮어쓰면
# 테스트가 임시 파일을 가리켜도 마이그레이션은 **진짜 데이터베이스**를 고친다.
DATABASE_URL_IN_USE = config.get_main_option("sqlalchemy.url", None) or DATABASE_URL
# `%` 를 두 번 적어 되돌린다. alembic 의 설정은 ConfigParser 이고 그것은 `%` 를
# 보간 문법으로 읽는다 — 비밀번호에 `%40`(=`@`) 같은 퍼센트 인코딩이 들어 있으면
# 접속을 해 보기도 전에 ValueError 로 죽는다. 읽는 쪽에서 다시 한 글자로 돌아오므로
# 주소 자체는 바뀌지 않는다.
config.set_main_option("sqlalchemy.url", DATABASE_URL_IN_USE.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 모델을 전부 등록해야 메타데이터가 완전해진다. 반쪽 메타데이터로 자동 생성을
# 돌리면 빠진 표를 「지워야 할 표」로 읽는다.
register_models()
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL_IN_USE,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite 는 컬럼 삭제나 CHECK 변경이 사실상 테이블 재생성이다. 배치
        # 모드가 그 재생성을 대신 해 준다. PostgreSQL 에서는 무해하다.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # 부르는 쪽이 연결을 넘겼으면 **그 연결로** 돈다. 주소만 받으면 새 엔진을
    # 열게 되는데, 그 주소는 부르는 쪽이 실제로 쓰는 데이터베이스가 아닐 수
    # 있다 — 테스트가 `db.base.engine` 을 메모리 엔진으로 바꿔 두었을 때가
    # 그렇다. 그때 마이그레이션은 개발자의 진짜 파일을 고친다.
    given = config.attributes.get("connection")
    if given is not None:
        _run(given)
        return

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        _run(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
