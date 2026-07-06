# python:3.11-slim은 멀티아치 이미지라 라즈베리파이 5(arm64, 64비트 OS)에서도 동일하게 빌드된다.
FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml requirements.txt ./
COPY src ./src
COPY scripts ./scripts

# gunicorn은 Windows에서 설치가 안 되므로 requirements.txt에는 넣지 않고 여기서만 설치한다
# (로컬 Windows 개발 환경의 pip install -e .는 그대로 유지).
RUN pip install --no-cache-dir -e . && pip install --no-cache-dir "gunicorn==23.0.0"

EXPOSE 5000

# 기본 CMD는 웹 서버. docker-compose.yml의 scheduler 서비스는 command를 오버라이드해
# 같은 이미지로 scripts/run_daily_update.py를 실행한다.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "stockapp_notion.webapp:app"]
