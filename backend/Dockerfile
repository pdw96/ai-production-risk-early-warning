FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Windows 체크아웃 등에서 실행 비트가 사라져도 동작하도록 컨테이너에서 다시 부여한다.
RUN chmod +x /app/docker-entrypoint.sh

# 접속 주소는 DATABASE_URL 로 준다(compose 가 넘긴다). 없으면 SQLite 파일로
# 떨어지며, 그 경로는 DATABASE_PATH 로 바꿀 수 있다.
ENV DATABASE_PATH=/app/production_risk.db

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
