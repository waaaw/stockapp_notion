# 라즈베리파이 5 설치 가이드 (주식 포트폴리오 앱 24시간 구동)

이 문서는 **처음부터 끝까지** 따라 하면 라즈베리파이 5에서 이 앱이 24시간 돌아가고, 폰에서도
안전하게 접속할 수 있게 되는 것을 목표로 한다. 리눅스/도커를 처음 다뤄도 그대로 따라올 수 있게
명령어를 전부 적어두었다.

> 이 앱은 데이터를 전부 Notion(클라우드)에 저장하므로, 라즈베리파이에는 별도의 하드디스크나
> 큰 저장공간이 필요 없다. "인터넷 되는 작은 상시 서버" 역할만 한다.

---

## 0. 준비물 (하드웨어)

- **라즈베리파이 5** (4GB 또는 8GB — 이 앱엔 4GB로 충분)
- **공식 27W USB-C 전원 어댑터** (파이 5는 전력을 많이 먹어 정품 전원 권장)
- **microSD 카드 32GB 이상** (또는 NVMe SSD + 어댑터 — SD보다 빠르고 안정적, 선택)
- microSD 리더기 (PC에서 OS 구울 때)
- 유선 랜 또는 Wi-Fi 환경
- (선택) 케이스 + 방열판/팬 — 파이 5는 발열이 있어 방열 권장

---

## 1. 라즈베리파이 OS 설치 (PC에서 SD카드 굽기)

1. PC에서 **Raspberry Pi Imager** 다운로드/설치: https://www.raspberrypi.com/software/
2. microSD를 PC에 꽂고 Imager 실행
3. **장치 선택**: `Raspberry Pi 5`
4. **운영체제 선택**: `Raspberry Pi OS (64-bit)` → **Lite** 버전 권장
   (Lite = 데스크톱 없는 서버용, 가볍고 이 앱 구동에 충분. 모니터 없이 SSH로만 쓸 것이므로 Lite가 적합)
5. **저장소 선택**: 꽂은 microSD
6. **다음** → **"설정을 편집하시겠습니까?"** 에서 반드시 **설정 편집**:
   - ✅ **호스트 이름**: 예) `stockpi`
   - ✅ **사용자 이름/비밀번호 설정**: 예) 사용자 `pi`, 원하는 비밀번호 (꼭 기억)
   - ✅ **무선 LAN 설정**: Wi-Fi 쓸 거면 SSID/비밀번호 + 국가 `KR`
   - ✅ **서비스 탭 → SSH 사용 → 비밀번호 인증 사용** 체크
   - (지역 설정: 시간대 `Asia/Seoul`, 키보드 `us` 권장)
7. **저장 → 쓰기**. 완료되면 SD를 빼서 라즈베리파이에 꽂는다.

---

## 2. 첫 부팅 & SSH 접속

1. 라즈베리파이에 SD카드 꽂고 랜선(또는 Wi-Fi 설정됨) 연결 후 전원 인가
2. 1~2분 부팅 대기
3. PC(윈도우)에서 **PowerShell** 또는 터미널을 열고 SSH 접속:
   ```powershell
   ssh pi@stockpi.local
   ```
   - `stockpi`는 1단계에서 정한 호스트 이름. `.local`이 안 되면 공유기 관리페이지에서 라즈베리파이의
     IP를 찾아 `ssh pi@192.168.0.xx` 형태로 접속
   - 처음 접속 시 `yes` 입력, 이어서 비밀번호 입력
4. 접속되면 최신 패키지로 업데이트:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

---

## 3. Docker 설치

```bash
# Docker 공식 설치 스크립트 (라즈베리파이 공식 권장 방식)
curl -fsSL https://get.docker.com | sh

# 현재 사용자(pi)를 docker 그룹에 추가해 sudo 없이 docker 사용
sudo usermod -aG docker $USER

# 그룹 변경 적용을 위해 로그아웃 후 재접속
exit
```
다시 접속:
```powershell
ssh pi@stockpi.local
```
설치 확인:
```bash
docker --version
docker compose version
```
두 명령이 버전을 출력하면 성공.

---

## 4. 앱 내려받기

Git으로 이 저장소를 클론한다:
```bash
sudo apt install -y git
cd ~
git clone https://github.com/waaaw/stockapp_notion.git
cd stockapp_notion
```

> 비공개 저장소라 인증을 물으면, GitHub 사용자명 + **Personal Access Token**(비밀번호 아님)을 입력한다.
> 또는 PC에서 `scp -r`로 폴더를 통째로 복사해도 된다:
> `scp -r D:\Develop\codex\stockapp_notion pi@stockpi.local:~/stockapp_notion`
> (이 경우 `.venv`, `logs/*.log`, `.git`는 빼고 복사하는 게 깔끔하다)

---

## 5. `.env` 작성 (가장 중요)

`.env.example`을 복사해 실제 값을 채운다:
```bash
cp .env.example .env
nano .env
```

`nano` 편집기에서 아래 값들을 채운다 (기존 PC에서 쓰던 `.env` 값을 그대로 옮기면 된다):

```ini
# Notion (필수) — PC에서 쓰던 값 그대로
NOTION_TOKEN=ntn_xxxxx
DB_STOCKS_ID=...
DB_TRANSACTIONS_ID=...
DB_PORTFOLIO_ID=...
DB_DIVIDENDS_ID=...
LOG_LEVEL=INFO

# 웹 UI — 외부(폰)에서 접속할 것이므로 아래를 채운다
WEB_HOST=0.0.0.0
WEB_PORT=5000
WEB_USERNAME=원하는아이디
WEB_PASSWORD=원하는_강한_비밀번호
# 로그인을 켜면 아래 키가 반드시 있어야 한다(없으면 앱이 시작 시 에러로 알려줌)
# 아무 긴 랜덤 문자열. 아래 명령으로 생성 가능:
#   python3 -c "import secrets; print(secrets.token_hex(32))"
FLASK_SECRET_KEY=여기에_생성한_랜덤문자열

# KIS (선택) — 쓰는 경우에만
KIS_APP_KEY=...
KIS_APP_SECRET=...
KIS_ACCOUNT_NO=...
KIS_IS_PAPER=true
```

`FLASK_SECRET_KEY` 랜덤값 생성이 필요하면 라즈베리파이에서:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```
출력된 문자열을 `.env`의 `FLASK_SECRET_KEY=` 뒤에 붙여넣는다.

저장: `Ctrl+O` → `Enter` → 종료 `Ctrl+X`

> ⚠️ `.env`에는 토큰/비밀번호가 들어 있다. `.gitignore`에 포함되어 있어 git에 올라가지 않는다.

---

## 6. 실행

```bash
docker compose up -d --build
```
- 처음엔 이미지 빌드(파이 5에서 5~15분 정도, pandas/numpy 컴파일로 시간이 걸릴 수 있음) 후 컨테이너가 뜬다
- `-d`는 백그라운드 실행, `--build`는 이미지 새로 빌드

상태 확인:
```bash
docker compose ps
```
`web`과 `scheduler` 두 서비스가 `running`(web은 `healthy`)이면 성공.

로그 확인:
```bash
docker compose logs -f web        # 웹 서버 로그 (Ctrl+C로 빠져나옴)
docker compose logs -f scheduler  # 스케줄러 로그
```

---

## 7. 접속 테스트 (집 안에서 먼저)

같은 집 Wi-Fi에 있는 PC/폰 브라우저에서:
```
http://stockpi.local:5000
```
(`.local`이 안 되면 `http://라즈베리파이IP:5000`)

로그인 화면이 뜨고, `.env`의 `WEB_USERNAME`/`WEB_PASSWORD`로 로그인되면 성공.

---

## 8. 외부(집 밖 LTE)에서 접속 — Tailscale (권장)

포트포워딩은 앱을 인터넷에 그대로 노출해 위험하다. **Tailscale**은 라즈베리파이와 폰을 사설
네트워크처럼 묶어주어, 포트포워딩·공인도메인·인증서 없이 안전하게 접속하게 해준다.

### 8-1. 라즈베리파이에 Tailscale 설치
```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```
출력되는 URL을 PC/폰 브라우저에서 열어 **Tailscale 계정으로 로그인**(구글 계정 등 무료).
연결되면 라즈베리파이의 Tailscale IP를 확인:
```bash
tailscale ip -4
```
예: `100.101.102.103`

### 8-2. 폰에 Tailscale 앱 설치
- 앱스토어/플레이스토어에서 **Tailscale** 설치 → 같은 계정으로 로그인
- 이제 폰이 LTE/외부망이어도 라즈베리파이와 연결됨

### 8-3. 폰에서 접속
폰 브라우저에서:
```
http://100.101.102.103:5000
```
(위에서 확인한 Tailscale IP 사용) → 로그인 → 어디서든 포트폴리오 확인 가능

---

## 9. 운영 (자주 쓰는 명령)

라즈베리파이 SSH 접속 후 `cd ~/stockapp_notion` 상태에서:

| 목적 | 명령 |
|---|---|
| 상태 확인 | `docker compose ps` |
| 웹 로그 보기 | `docker compose logs -f web` |
| 스케줄러 로그 | `docker compose logs -f scheduler` |
| 앱 로그 파일 | `tail -f logs/app.log` |
| 재시작 | `docker compose restart` |
| 중지 | `docker compose down` |
| 시작 | `docker compose up -d` |
| 코드 업데이트 후 재배포 | `git pull && docker compose up -d --build` |
| `.env` 수정 반영 | `.env` 편집 후 `docker compose up -d`(재빌드 불필요) |

- **자동 갱신**: `scheduler` 컨테이너가 매일 16:00(KST, 장 마감 후)에 현재가·포트폴리오를
  자동 갱신한다. 라즈베리파이가 켜져 있는 한 PC를 안 켜도 계속 돈다.
- **자동 재시작**: `restart: unless-stopped` 설정으로 라즈베리파이를 재부팅해도 컨테이너가
  자동으로 다시 뜬다.
- 웹에서 "일일 갱신" 버튼을 눌러 수동 갱신도 언제든 가능.

---

## 10. 문제 해결

| 증상 | 확인 |
|---|---|
| `ssh: could not resolve hostname` | `.local` 대신 공유기에서 IP 확인해 `ssh pi@192.168.x.x` |
| 앱 시작이 안 되고 FLASK_SECRET_KEY 에러 | 로그인을 켰으면 `.env`에 `FLASK_SECRET_KEY`를 채워야 함(5장 참고) |
| `docker compose logs web`에 Notion 401 | `.env`의 `NOTION_TOKEN`이 맞는지, Integration이 페이지에 연결됐는지 확인 |
| 빌드가 매우 오래 걸림/멈춤 | 파이 5에서 pandas/numpy 컴파일은 원래 느림. SD보다 NVMe SSD가 훨씬 빠름 |
| 폰에서 Tailscale IP로 접속 안 됨 | 폰 Tailscale 앱이 켜져 있고 같은 계정인지, `tailscale status`로 라즈베리파이가 온라인인지 확인 |
| 현재가가 0 | "현재가 갱신" 버튼 클릭 또는 다음 16:00 자동 갱신 대기 |

---

## 부록: NVMe SSD로 부팅 (선택, 성능 향상)

파이 5는 M.2 HAT+를 달면 NVMe SSD로 부팅할 수 있다. SD카드보다 빠르고 수명이 길어 24시간
서버용으로 권장되지만, 필수는 아니다. SD카드로도 이 앱은 문제없이 돌아간다. 필요해지면 별도로
안내 가능.
