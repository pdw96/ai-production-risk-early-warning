FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Windows 체크아웃 등에서 실행 비트가 사라져도 동작하도록 컨테이너에서 다시 부여한다.
RUN chmod +x /app/docker-entrypoint.sh

# 볼륨에 DB를 두려면 DATABASE_PATH를 재정의한다. 비워 두면 /app/production_risk.db를 쓴다.
ENV DATABASE_PATH=/app/production_risk.db

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
