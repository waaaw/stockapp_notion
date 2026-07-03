# 테스트 매뉴얼

이 문서는 `stockapp_notion` 프로젝트가 내 PC/내 Notion 워크스페이스에서 실제로 잘 동작하는지
직접 확인하기 위한 절차입니다. 순서대로 따라 하시면 됩니다.

---

## 0. 사전 준비 확인

터미널(PowerShell 또는 Git Bash)에서 프로젝트 폴더로 이동합니다.

```powershell
cd D:\Develop\codex\stockapp_notion
```

아래 3가지가 준비되어 있어야 합니다. 하나라도 없다면 [README.md](README.md)의 "설치" ~ "1단계"를 먼저 진행하세요.

- [ ] `.venv` 폴더 존재 (가상환경)
- [ ] `.env` 파일에 `NOTION_TOKEN` 값이 채워져 있음
- [ ] `.env` 파일에 `DB_STOCKS_ID`, `DB_TRANSACTIONS_ID`, `DB_PORTFOLIO_ID`, `DB_DIVIDENDS_ID` 4개가 모두 채워져 있음

가상환경을 활성화합니다.

```powershell
.\.venv\Scripts\Activate.ps1
```
(Git Bash라면: `source .venv/Scripts/activate`)

---

## 1. 단위 테스트 실행 (Notion 접속 없이 계산 로직만 확인)

```powershell
python -m pytest tests/ -v
```

**기대 결과**: `6 passed` 메시지와 함께 아래 6개 테스트가 모두 `PASSED`로 나와야 합니다.
- 평균단가 계산(단일 매수/가중평균/부분매도/전량매도)
- 총거래금액 계산(매수/매도)

여기서 실패한다면 Notion 연결 문제가 아니라 코드 자체 문제이니, 에러 메시지를 저에게 알려주세요.

---

## 2. 종목 등록 테스트

```powershell
python -m stockapp_notion.cli add-stock --name 카카오 --code 035720 --market 코스피 --sector IT --currency KRW
```

**확인 방법**:
1. 터미널에 `종목 등록 완료: 카카오(035720)` 로그가 찍히는지 확인
2. Notion에서 "종목 마스터" 데이터베이스를 열어 "카카오" 행이 새로 생겼는지 눈으로 확인

같은 명령을 한 번 더 실행해보세요 — 이미 등록된 종목이면 중복 생성되지 않고
`이미 등록되어 있습니다. 건너뜁니다.` 로그가 나오는 게 정상입니다(멱등성 확인).

---

## 3. 매매내역 입력 테스트

```powershell
python -m stockapp_notion.cli add-transaction --code 035720 --type 매수 --qty 5 --price 50000 --fee 50 --date 2026-07-04
```

**확인 방법**:
1. 터미널에 `매매내역 등록`과 `포트폴리오 갱신` 로그가 순서대로 찍히는지 확인 (매매 입력 시 포트폴리오도 자동 재계산됨)
2. Notion "매매 내역" DB에 새 행이 생겼는지 확인 (종목=카카오, 매매구분=매수, 수량=5, 단가=50000, 총거래금액=250050)
3. Notion "포트폴리오 요약" DB에 카카오 행이 생겼는지 확인 (보유수량=5, 평균단가=50000)
   - 이 시점엔 아직 현재가를 안 받아왔으니 평가금액=0, 평가손익은 음수로 나오는 게 정상입니다 (4단계에서 해결됨)

추가로 매도도 한 번 테스트해보면 좋습니다:
```powershell
python -m stockapp_notion.cli add-transaction --code 035720 --type 매도 --qty 2 --price 55000 --fee 30 --date 2026-07-05
```
→ 포트폴리오 요약의 보유수량이 5 → 3으로 줄고, 평균단가(50000)는 그대로 유지되는지 확인하세요.

---

## 3-A. 웹 UI로 입력해보기 (선택)

CLI 대신 브라우저 폼으로 위 2~3단계(종목 등록, 매매내역, 배당금)를 반복해볼 수 있습니다.

```powershell
python -m stockapp_notion.webapp
```

터미널에 `Running on http://127.0.0.1:5000` 같은 메시지가 뜨면 브라우저에서
**http://127.0.0.1:5000** 으로 접속하세요.

**확인 방법**:
1. "종목 등록" 폼에 값을 채우고 등록 버튼 클릭 → 초록색 성공 메시지가 뜨고, 페이지 아래 "등록된 종목" 표에 즉시 반영되는지 확인
2. "매매내역 입력" 폼의 종목 드롭다운에 방금 등록한 종목이 보이는지 확인 → 매수 입력 후 성공 메시지 확인
3. 상단 "현재가 갱신" / "포트폴리오 재계산" / "일일 갱신" 버튼을 각각 눌러보고, 표의 "현재가" 열이 갱신되는지 확인
4. Notion 앱에서도 동일한 데이터가 반영됐는지 대조 확인

종료하려면 터미널에서 `Ctrl+C`를 누르세요. (인증이 없는 로컬 전용 서버이므로 외부에 노출하지 마세요.)

---

## 4. 현재가 갱신 테스트

```powershell
python -m stockapp_notion.cli update-prices
```

**확인 방법**:
1. 터미널에 `현재가 갱신: 카카오(035720) -> 숫자` 로그가 종목별로 찍히는지 확인
2. 마지막 줄 `현재가 갱신 완료: 성공 N건, 실패 0건`에서 실패 건수가 0인지 확인
   - 실패가 있다면 종목코드/시장구분 조합이 잘못됐거나(예: 코스닥 종목인데 코스피로 등록) 야후 파이낸스에 없는 코드일 수 있습니다
3. Notion "종목 마스터" DB에서 해당 종목의 "현재가"가 채워졌는지 확인

---

## 5. 포트폴리오 재계산 테스트

```powershell
python -m stockapp_notion.cli sync-portfolio
```

**확인 방법**: Notion "포트폴리오 요약" DB에서 4단계에서 받아온 현재가를 반영해
평가금액/평가손익/수익률(%)이 정상적인 숫자로 바뀌었는지 확인합니다.

직접 계산기로 검산해보세요: `평가금액 = 보유수량 × 현재가`, `평가손익 = 평가금액 - (보유수량 × 평균단가)`

---

## 6. 배당금 입력 테스트 (선택)

```powershell
python -m stockapp_notion.cli add-dividend --code 035720 --date 2026-07-01 --pretax 3000 --posttax 2538
```

**확인 방법**: Notion "배당금 내역" DB에 새 행이 생겼는지 확인 (세전 3000, 세후 2538)

---

## 7. 일괄 배치 테스트 (실제 스케줄러가 매일 실행하는 것과 동일)

```powershell
python -m stockapp_notion.cli daily-update
```

내부적으로 4단계(update-prices) + 5단계(sync-portfolio)를 순서대로 실행합니다.
에러 없이 끝나고 Notion에 최신 값이 반영되면 정상입니다.

---

## 8. 자동 스케줄링(작업 스케줄러) 동작 확인

이미 `StockAppNotionDailyUpdate`라는 이름으로 매일 16:00 실행되도록 등록되어 있습니다.

**등록 상태 확인**:
```powershell
schtasks /Query /TN "StockAppNotionDailyUpdate" /V /FO LIST
```
`Scheduled Task State: Enabled`, `Next Run Time`이 오늘/내일 16:00으로 찍히는지 확인하세요.

**수동으로 즉시 1회 실행해보기** (16:00까지 기다리지 않고 바로 테스트):
```powershell
schtasks /Run /TN "StockAppNotionDailyUpdate"
```
몇 초 후 아래 로그 파일에 실행 결과가 쌓였는지 확인합니다:
```powershell
Get-Content D:\Develop\codex\stockapp_notion\logs\cron.log -Tail 20
```

**마지막 실행이 성공했는지 확인**:
```powershell
schtasks /Query /TN "StockAppNotionDailyUpdate" /V /FO LIST | Select-String "Last Run Time|Last Result"
```
`Last Result: 0`이면 성공입니다. 0이 아니면 실패이니 `logs/cron.log`와 `logs/app.log`를 확인하세요.

---

## 9. 로그 파일로 실패 이력 확인하기

모든 실행 로그는 `logs/app.log`에 쌓입니다 (성공/실패 모두 기록, 로테이션으로 최대 5개 x 2MB 유지).

```powershell
Get-Content D:\Develop\codex\stockapp_notion\logs\app.log -Tail 50
```

`[ERROR]`로 시작하는 줄이 있는지 찾아보세요:
```powershell
Select-String -Path D:\Develop\codex\stockapp_notion\logs\app.log -Pattern "ERROR"
```

---

## 10. 문제가 생겼을 때 체크리스트

| 증상 | 확인할 것 |
|---|---|
| `RuntimeError: 환경변수 ...가 설정되지 않았습니다` | `.env` 파일에 해당 값이 채워져 있는지, 오타는 없는지 확인 |
| `APIResponseError: unauthorized` | `NOTION_TOKEN`이 올바른지, Integration이 해당 페이지에 연결(Connect)되어 있는지 확인 |
| `종목코드 XXXXXX를 종목 마스터 DB에서 찾을 수 없습니다` | `add-transaction`/`add-dividend` 전에 `add-stock`으로 먼저 등록했는지 확인 |
| 현재가 갱신 실패 (`시세 조회 실패`) | 종목코드가 실제 존재하는지, 시장구분(코스피/코스닥/나스닥/NYSE)이 맞는지 확인. 코스피↔코스닥이 바뀌면 티커(.KS/.KQ)가 틀려서 실패함 |
| 작업 스케줄러가 안 도는 것 같음 | PC가 그 시간에 꺼져 있었는지, `Last Result` 값이 0인지, `logs/cron.log`에 최근 기록이 있는지 확인 |

---

## 부록: 테스트 데이터 정리하기

위 과정에서 만든 "카카오" 테스트 데이터가 필요 없다면, Notion 앱/웹에서 직접 해당 행들을
삭제(또는 휴지통으로 이동)하면 됩니다 — 이 프로젝트의 스크립트는 삭제 기능을 제공하지 않으므로
Notion UI에서 직접 지우는 것이 안전합니다.
