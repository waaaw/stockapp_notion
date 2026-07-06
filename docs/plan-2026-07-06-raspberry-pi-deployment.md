# 계획: 라즈베리파이 5 + Docker 배포 (외부 접속 포함)

## Context

지금까지는 Windows PC에서 `python -m stockapp_notion.webapp`를 수동/스케줄러로 띄워 썼다.
이 방식은 PC가 꺼져 있으면 갱신도, 접속도 안 된다는 한계가 있다. 사용자가 보유한
ipTIME NAS2dual은 사양(ARM, 2GB RAM)과 Docker 미지원으로 이 앱을 안정적으로 돌리기
부적합하다고 판단했고, **라즈베리파이 5**로 24시간 상시 구동하기로 했다. 데이터는 전부
Notion(클라우드)에 있으므로 라즈베리파이의 저장공간/RAID는 필요 없고, "인터넷 되는 저전력
상시 리눅스 박스" 역할만 하면 된다.

또한 사용자는 **폰 등 외부에서도 접속**하고 싶다고 했다. 현재 웹 UI는 인증이 전혀 없고
127.0.0.1 전용이라, 외부 노출 전 반드시 로그인 기능을 추가해야 한다.

## 아키텍처

```
[Notion] <--> [라즈베리파이 5, Docker Compose]
                 ├─ web 컨테이너: gunicorn + Flask (로그인 필요)
                 └─ scheduler 컨테이너: 기존 scripts/run_daily_update.py
                     (APScheduler, 매일 16:00 daily-update 그대로 재사용)
                 ▲
                 │ Tailscale (권장) 또는 리버스 프록시+포트포워딩
              [폰/PC에서 접속]
```

Windows Task Scheduler(`daily_update.bat`)는 더 이상 필요 없다 — 스케줄링은 이미 만들어둔
`scripts/run_daily_update.py`가 담당(코드 변경 없이 그대로 컨테이너로 실행).

## 변경/신규 사항

### 1. 웹 UI 로그인 (외부 노출 전 필수)
- `src/stockapp_notion/auth.py` 신규: 세션 기반 간단 로그인. `.env`의 `WEB_USERNAME`/`WEB_PASSWORD`와
  `secrets.compare_digest`로 비교(타이밍 공격 방지). `@app.before_request`로 `/login`, 정적 리소스를
  제외한 모든 라우트를 보호.
- `templates/login.html` 신규 (기존 다크 테마 톤 유지).
- `config.py`에 `web_username`/`web_password` 추가.

### 2. 호스트/포트 설정화
- `config.py`에 `web_host`(기본 `127.0.0.1`), `web_port`(기본 `5000`) 추가.
- `webapp.py`의 `main()`이 하드코딩 대신 이 설정을 사용. Docker에서는 `WEB_HOST=0.0.0.0`으로
  설정(컨테이너 내부 바인딩이며, 실제 외부 노출 여부는 Tailscale/포트 매핑이 결정).

### 3. Docker 이미지 + Compose
- `Dockerfile`: `python:3.11-slim`(라즈베리파이 5의 64비트 OS와 호환되는 멀티아치 이미지) 기반,
  `pip install -e .` + `gunicorn`(Windows에서 안 깔리므로 requirements.txt엔 넣지 않고 Dockerfile에서만
  설치). `CMD`는 gunicorn으로 `stockapp_notion.webapp:app` 서빙.
- `.dockerignore`: `.venv`, `.git`, `logs/*.log`, `.env`(이미지에 굽지 않고 런타임에 마운트) 등 제외.
- `docker-compose.yml`: `web`(gunicorn, 포트 5000 노출) + `scheduler`(`python scripts/run_daily_update.py`)
  두 서비스. 둘 다 `env_file: .env` 공유, `./logs`와 KIS 토�큰 캐시 파일을 볼륨 마운트해 컨테이너
  재시작에도 로그/토큰이 유지되게 함. `restart: unless-stopped`.

### 4. 외부 접속 방법 (문서화, 코드 아님)
- **권장: Tailscale** — 포트포워딩/공인 도메인/인증서 없이 라즈베리파이와 폰에 각각 설치하면
  사설 VPN처럼 연결됨. 공격 표면이 없어 개인용으로 가장 안전하고 간단.
- 대안: DDNS + 라우터 포트포워딩 + Caddy/nginx 리버스 프록시(자동 HTTPS)로 진짜 공인 URL 노출.
  Tailscale보다 설정이 많고 공격 표면도 커진다 — 필요할 때만.
- 어느 쪽이든 위 1번(로그인)은 방어의 한 겹으로 유지.

## 배포 코드 재점검 후 개선 (2026-07-06 추가)
- **[버그 수정] 멀티 워커 세션 깨짐 방지**: gunicorn `--workers 2` 환경에서 `FLASK_SECRET_KEY`가
  없으면 워커마다 다른 랜덤 키가 생겨 로그인이 간헐적으로 풀린다. 로그인을 켠 경우(web_auth_enabled)
  `FLASK_SECRET_KEY`가 없으면 앱 시작 시 `RuntimeError`로 조기 실패하도록 함.
- **/health 엔드포인트 추가**(인증 우회): 컨테이너 헬스체크/모니터링용. `docker-compose.yml`의 web
  서비스에 healthcheck 연결.
- **세션 쿠키 하드닝**: `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE="Lax"` 명시.
- **gunicorn 버전 고정**(`gunicorn==23.0.0`) — 재현성.
- **이미지 중복 빌드 제거**: web/scheduler가 `image: stockapp-notion:local`을 공유해 한 번만 빌드.

## 검증 방법 (완료)
1. `pytest tests/` 18개 전체 통과, `WEB_USERNAME`/`WEB_PASSWORD` 미설정 시 기존과 동일하게
   인증 없이 동작(회귀 없음) 확인.
2. `WEB_USERNAME=testuser WEB_PASSWORD=testpass`로 실행해 로그인 플로우 실검증:
   미인증 `/` 접근 → 302 `/login` 리다이렉트, 오답 로그인 → 계속 차단, 정답 로그인 → `/` 200,
   로그아웃 후 다시 차단됨을 curl로 확인.
3. Docker가 이 Windows 기기에 없어 `docker build`/`docker compose up`은 직접 실행하지 못함.
   대신 Dockerfile과 동일한 순서(pyproject.toml+requirements.txt+src 복사 → `pip install -e .`)를
   별도 클린 venv에서 재현해 설치·임포트가 정상임을 확인했고, `docker-compose.yml`은 PyYAML로
   문법을 파싱 검증함. **실제 `docker build`/`docker compose up -d`는 라즈베리파이에서 사용자가
   직접 실행해 확인 필요.**
