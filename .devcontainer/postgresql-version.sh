#!/usr/bin/env bash
# 운영·CI·개발이 보는 **PostgreSQL 판 번호. 여기 한 곳에만 적는다.**
#
# 두 곳에서 쓴다 — 놓는 쪽(`install-postgresql.sh`)과 고르는 쪽(`database.sh`).
# 놓기만 하고 고를 때 확인하지 않으면, 16을 깔아 놓고도 5432를 지키던 15에
# 붙어서 돈다(실측 2026-09-09: 그때 `database.sh` 는 "PostgreSQL 15/main 를
# 기동합니다" 라고 답했다). 두 곳이 각자 숫자를 들고 있으면 언젠가 어긋나므로
# 숫자는 하나만 둔다.
#
# `compose.yaml` 의 이미지 태그와 같아야 하며, 그것은 검사가 지킨다.
#
# 이 파일은 값만 두는 자리다 — 읽어 가는 쪽에서 쓰므로 여기서는 쓰이지 않는다.
# shellcheck disable=SC2034
PRODUCTION_RISK_POSTGRESQL_MAJOR=16
