# 계획: stockapp_notion 실사용 개선 + KIS(한국투자증권) 자동 자산관리 연동

## Context (왜 하는가)

`D:\Develop\codex\stockapp_notion`은 지금까지 데모/검증 수준으로 만들어졌고, 이제 사용자가
**실제 본인 주식 포트폴리오를 지속적으로 관리하는 용도**로 쓰고자 한다. 두 가지 요청:

1. 실사용 관점에서 코드베이스를 리뷰하고 개선한다.
2. 원래 요청한 "삼성증권 API" 연동은 **삼성증권이 개인용 Open API를 제공하지 않아**(기관/거액고객
   전용) 불가능함을 확인했다. 대안으로 개인이 신청 가능하고 공식 Python 지원이 있는
   **한국투자증권(KIS) Open API**로 방향을 정했다(사용자 확인 완료). 목표는 실제 보유
   종목/체결내역을 자동으로 가져와 지금처럼 매번 손으로 CLI/웹 폼에 입력하지 않아도 되게 하는 것.

리뷰 결과 발견한 핵심 문제: 매매내역을 잘못 입력해도 고칠 방법이 없고, 매도 시 실현손익이
사라지며(평가손익은 현재 보유분에 대해서만 계산), 배당금이 별도 DB에만 있고 수익률 계산에
전혀 반영되지 않는다. 이 세 가지가 "실제 자산관리"에 가장 크게 영향을 준다.

사용자 확인 사항:
- KIS 연동 방식: **옵션 2(자동 거래 임포트)** — KIS 체결내역을 기존 매매내역 DB에 자동으로
  채워 넣고, 기존 계산 파이프라인(포트폴리오 재계산, 실현손익 등)을 그대로 재사용한다.
- KIS 모의투자(paper trading) **아직 미등록** — 개발 착수 전 사용자가 KIS 앱/HTS에서 먼저
  신청해야 한다 (사전 준비 사항으로 아래 명시).
- USD 종목(나스닥/NYSE) 보유 계획 **없음** — 다중통화 처리는 우선순위를 낮춰 이번 범위에서
  제외하고, 나중에 필요해지면 별도로 진행한다.
- 매매내역 수정/삭제: **전용 CLI+웹 UI 필요** — Notion 직접 수정 + 재계산 버튼만으로는 부족하다고
  판단.

---

## Part A. 기존 시스템 개선 (실사용 관점 우선순위)

### A-1. 공용 Notion 속성 추출 헬퍼 정리 (선행 작업, 위험 없음)
`portfolio.py`와 `webapp.py`가 `_prop_number`/`_title`/`_rich_text`/`_select_name`을 각각
따로 정의하고 있다(완전 중복). 새 파일 `src/stockapp_notion/notion_helpers.py`로 이관:
`prop_title`, `prop_rich_text`, `prop_select_name`, `prop_number` (언더스코어 제거, 공용 API로).
`portfolio.py`, `webapp.py`, `prices.py`(현재 인라인 추출 로직 있음)가 이를 import해서 쓰도록 수정.
동작 변화 없는 순수 리팩터링이라 가장 먼저 진행 — 이후 변경들의 위험을 줄인다.

### A-2. 입력값 검증
새 파일 `src/stockapp_notion/validation.py`:
- `validate_positive(value, field_name)` — 수량/단가는 0 초과
- `validate_non_negative(value, field_name)` — 수수료는 0 이상
- `validate_date_str(date_str)` — `YYYY-MM-DD` 형식 파싱 실패 시 명확한 에러

`transactions.add_transaction`, `dividends.add_dividend`, `stocks.add_stock` 맨 앞에서 호출해
Notion에 쓰기 전에 실패시킨다. `cli.py`(예외 시 로그+`sys.exit(1)`)와 `webapp.py`(예외 시
flash 메시지)는 이미 일반 `Exception`을 처리하므로 추가 배관 작업 불필요.

### A-3. 매매내역 수정/삭제 (CLI + 웹 UI) — 사용자 확정 요구사항
- `transactions.py`에 추가:
  - `update_transaction(transaction_page_id, *, trade_date=None, buy_sell=None, qty=None, price=None, fee=None, client=None)` — 변경된 필드만 반영, `총거래금액`도 재계산
  - `delete_transaction(transaction_page_id, client=None)` — Notion API는 완전삭제가 없으므로 `pages.update(archived=True)`(휴지통 이동, 되돌리기 가능)
  - `list_transactions_for_stock`는 이미 있으니 그대로 활용해 특정 종목의 매매내역 목록을 보여줄 수 있음
- 수정/삭제 후에는 `sync_all_portfolios()` 대신 **해당 종목만** `sync_portfolio_for_stock()`으로
  재계산(전체 재계산 비효율 일부 개선, 부수 효과)
- `cli.py`: `list-transactions --code CODE` (조회, 페이지ID 확인용), `edit-transaction --transaction-id ID [--qty ...] [--price ...] ...`, `delete-transaction --transaction-id ID`
- `webapp.py` + `templates/index.html`: 새 라우트 `/transactions/<code>` — 해당 종목의 매매내역을
  표로 보여주고 각 행에 수정 폼/삭제 버튼. 삭제는 실수 방지를 위해 확인 단계(JS `confirm()`) 포함.
  종목 선택은 기존 "보유 현황" 표나 매매내역 입력 폼의 드롭다운에서 종목명 클릭 시 이 페이지로
  이동하는 링크 추가.
- 매매구분 매직 스트링 정리: `transactions.py`에 `BUY = "매수"`, `SELL = "매도"`, `TRADE_TYPES = (BUY, SELL)` 상수 추가, `cli.py`/`portfolio.py`의 하드코딩된 비교문을 이 상수로 교체(템플릿의 HTML 옵션 문자열은 그대로 둠).
- 중복 매매 입력 감지: `find_duplicate_transaction(stock_page_id, trade_date, buy_sell, qty, price)`을
  `add_transaction` 호출 전 체크 — **경고만 하고 차단하지 않음**(대량주문 분할 등 정당한 동일 조건
  재입력이 있을 수 있으므로). CLI는 경고 출력 후 계속 진행, 웹은 flash 경고 후 계속 진행.

### A-4. 매도 시 실현손익 추적
`portfolio.py`의 `compute_holding()`은 매도 시 수량/평균단가만 갱신하고 그 매도 건의 손익은
버린다. 내부 accumulator를 공유하는 두 함수로 분리:
- `compute_holding(transactions) -> Holding` — 기존 시그니처 유지(기존 6개 단위테스트 그대로 통과)
- `compute_realized_gains(transactions) -> list[RealizedGain]` (새 `@dataclass`: trade_date, qty,
  sell_price, avg_cost_at_sale, fee, realized_pnl) — 매도 시점의 평균단가를 기준으로 계산
- 두 함수가 내부적으로 같은 순회 로직(`_replay_transactions`)을 공유해 로직 중복 방지
- 포트폴리오 요약 DB에 `누적실현손익` Number 속성 추가 (기존 DB에 속성만 추가, `client.data_sources.update` 사용 — `docs/2026-07-03.md`에 기록된 방식과 동일). 재사용 가능한 헬퍼
  `ensure_property(client, data_source_id, prop_name, prop_schema)`를 `notion_api.py`에 추가해
  이번과 다음(A-5) 스키마 추가에 공용으로 사용.
- `sync_portfolio_for_stock`이 `누적실현손익`도 계산해 기록. 웹 UI "보유 현황" 표/합계에도
  실현손익 열 추가.
- 실현손익은 **누적(전체 기간) 값만** 저장(연도별 세금용 분리는 이번 범위 밖 — 필요해지면 거래일자로
  필터링해 추가 가능하다고 문서에 남김).

### A-5. 배당금을 총수익률에 반영
`dividends.py`에 `total_dividends_for_stock(stock_page_id, client=None) -> float` 추가 (세후배당금
합산, `DB_DIVIDENDS_ID` 미설정 시 0 반환 — 예외 아님). `sync_portfolio_for_stock`이
`총수익(배당포함)` = 평가손익 + 누적실현손익 + 누적배당금, `총수익률(%)`을 추가 계산해 기록.
웹 UI에 기존 "평가손익"과 별도로 "총수익(배당포함)" 행 추가(둘 다 보여줌, 대체 아님).

### 이번 범위에서 제외(사용자 확인)
- **다중통화 처리(A-6)**: USD 종목 보유 계획 없음 → 스킵. 코드에는 이미 종목별 `통화` 값이 있으니
  나중에 필요해지면 `list_portfolio_summary()`에 `currency` 키 추가 + 통화별 합계 분리만 하면 됨(설계는
  문서에 남기되 구현하지 않음).
- **히스토리 스냅샷**: 이번 범위 밖. 필요해지면 5번째 DB(포트폴리오 스냅샷, 날짜+합계값만) 추가로
  나중에 독립적으로 진행 가능.
- **FIFO 방식 전환**: 기존 이동가중평균 방식 유지(설계상 결정 유지, 세무상 필요해지면 재검토).

### Part A 순서
A-1(공용 헬퍼) → A-2(검증) → A-3(수정/삭제+상수+중복감지) → A-4(실현손익) → A-5(배당 반영)

---

## Part B. KIS(한국투자증권) Open API 연동 — 자동 자산현황 관리

### 사전 준비 (사용자 액션, 개발 착수 전 필요)
1. KIS 증권 계좌에서 **모의투자(paper trading) 신청** — 앱/HTS에서 별도 등록 필요(현재 미등록 확인됨)
2. https://apiportal.koreainvestment.com/apiservice 에서 Open API 신청 → `appkey`/`appsecret` 발급
3. 실계좌 계좌번호(8자리+상품코드 2자리) 확보

### B-1. 인증/설정
`config.py`의 `Settings`에 기존 패턴(`_require` + lazy property)으로 추가:
`kis_app_key`, `kis_app_secret`, `kis_account_no`, `kis_is_paper`(기본값 `true` — 안전을 위해
모의투자를 기본으로). `.env.example`에 `KIS_APP_KEY`/`KIS_APP_SECRET`/`KIS_ACCOUNT_NO`/`KIS_IS_PAPER=true` 추가.

### B-2. 새 모듈 `src/stockapp_notion/kis_api.py`
`notion_api.py`와 동일한 구조(클라이언트/인증 헬퍼 + 재시도 래퍼)로 미러링:
- 토큰 발급/캐싱: KIS 토큰은 수명이 길지만(약 24시간, 구현 시점에 공식 문서로 재확인 필요)
  발급 자체가 별도로 제한됨 → **디스크 캐시** 필요(스케줄러가 매일 새 프로세스로 실행되므로
  메모리 캐시만으론 매번 재발급하게 됨). `.kis_token_cache.json`에 `{access_token, expires_at,
  is_paper}` 저장, `.gitignore`에 추가.
- `call_with_retry(fn, *args, **kwargs)` — `notion_api.call_with_retry`와 동일한 형태(429/5xx
  지수 백오프, 최대 5회), `logging_config.get_logger` 사용
- `fetch_account_balance(client=None) -> dict` — KIS 잔고조회(주식잔고조회) 엔드포인트 호출,
  종목코드/종목명/보유수량/매입평균가/평가금액/평가손익 반환
- `fetch_execution_history(start_date, end_date, client=None) -> list[dict]` — 체결내역 조회
  (구현 시점에 정확한 TR ID를 KIS 공식 문서로 재확인 — 브로커가 종종 TR ID를 개정함)

### B-3. 매매내역 자동 임포트 (옵션 2 — 사용자 확정 방식)
- Transactions DB에 `KIS주문번호`(또는 체결번호) rich_text 속성 추가(A-4에서 만든 `ensure_property`
  헬퍼 재사용) — 중복 임포트 방지용 idempotency key
- `kis_api.py`의 체결내역을 순회하며, 해당 KIS주문번호가 이미 Transactions DB에 없는 건만
  `transactions.add_transaction`으로 생성(출처 구분이 필요하면 `출처` select 속성 "KIS자동"/"수동"
  추가도 고려 가능 — 필요시에만)
- 새 명령: `cli.py`의 `kis-import-transactions --since DATE`, 웹 UI에도 대응 버튼 추가

### B-4. 잔고 교차검증 (첫 마일스톤, 안전한 시작점)
- `fetch_account_balance()` 결과와 Notion 매매내역 기반 계산 결과(`sync_all_portfolios()`가 이미
  계산하는 값)를 비교해 **불일치를 로그로만 남기고 아무것도 덮어쓰지 않음** — 리스크 없이
  "내 수기 기록이 실제 계좌와 맞는지" 확인 가능한 첫 실용적 결과물
- 새 명령: `cli.py`의 `kis-check-balance`

### B-5. 마일스톤 순서
1. **마일스톤 1 (모의투자로 검증)**: B-1, B-2(`fetch_account_balance`만), B-4(교차검증, 읽기전용)
   — 모의투자 계좌로 전부 검증 완료 후에만 실계좌(`KIS_IS_PAPER=false`)로 전환
2. **마일스톤 2**: B-2(`fetch_execution_history`), B-3(자동 임포트+중복방지) — 마일스톤 1이
   안정적으로 돌아간 뒤 진행
3. **마일스톤 3 (나중, 스트레치)**: WebSocket 실시간 체결 push — 하루 1회 배치와 다른 상시 실행
   구조가 필요해서 별도 프로세스로 다뤄야 함. 이번 계획 범위 밖, 필요성 재확인 후 별도 진행.

### B-6. 기존 스케줄러와의 연결
`cli.py`의 `cmd_daily_update`에 `if settings.kis_app_key:` 가드로 KIS 단계(임포트→잔고체크)를
추가 — KIS 미설정 사용자도 기존처럼 문제없이 동작(배당금 DB와 동일한 선택적 기능 패턴).
순서: KIS 임포트 → 현재가 갱신 → 포트폴리오 재계산 (당일 신규 거래가 당일 재계산에 반영되도록).
`schtasks` 등록 자체는 변경 불필요.

**읽기 전용 원칙**: 이 연동은 KIS의 조회(잔고/체결) 엔드포인트만 호출하고, 주문 실행 엔드포인트는
절대 호출하지 않는다 — 이 도구가 자동으로 매매를 실행할 이유가 없다.

---

## 변경/신규 파일 요약

| 파일 | 변경 내용 |
|---|---|
| `src/stockapp_notion/notion_helpers.py` (신규) | 공용 속성 추출 헬퍼 |
| `src/stockapp_notion/validation.py` (신규) | 입력값 검증 함수 |
| `src/stockapp_notion/transactions.py` | 검증 호출, 상수, `update_transaction`/`delete_transaction`/`find_duplicate_transaction` 추가 |
| `src/stockapp_notion/portfolio.py` | 헬퍼 이관, `compute_realized_gains`/`RealizedGain`, 실현손익·총수익 계산 |
| `src/stockapp_notion/dividends.py` | `total_dividends_for_stock` 추가 |
| `src/stockapp_notion/notion_api.py` | `ensure_property` 헬퍼 추가 |
| `src/stockapp_notion/kis_api.py` (신규) | KIS 인증/조회/재시도 |
| `src/stockapp_notion/config.py` | KIS 관련 설정 추가 |
| `src/stockapp_notion/cli.py` | edit/delete/list-transactions, kis-check-balance, kis-import-transactions 명령 추가 |
| `src/stockapp_notion/webapp.py` + `templates/index.html` | 매매내역 목록/수정/삭제 라우트+화면, 실현손익/총수익 표시 |
| `.env.example`, `.gitignore` | KIS 설정 키, 토큰 캐시 파일 제외 |
| `tests/test_portfolio.py` | `compute_realized_gains` 단위테스트 추가 |

## 검증 방법
1. `pytest tests/` — 기존 6개 + 신규 실현손익/검증 테스트 통과 확인 (리팩터링 후에도 회귀 없는지)
2. CLI로 실제 Notion 워크스페이스 대상: `list-transactions` → `edit-transaction`으로 수정 →
   보유 현황에 반영 확인 → `delete-transaction`으로 삭제 → 반영 확인
3. 매수 후 매도 시나리오로 `누적실현손익`이 정확한지 직접 계산해 검증(기존 세션에서 검증했던
   방식과 동일하게 삼성전자 등으로 테스트)
4. 배당 입력 후 "총수익(배당포함)"이 배당금만큼 늘어나는지 확인
5. 웹 UI: 새 매매내역 목록 페이지에서 수정/삭제 후 "보유 현황" 표가 즉시 갱신되는지 확인
6. KIS는 **모의투자 계좌 등록 후** `kis-check-balance`로 먼저 검증, 값이 합리적으로 나오는지
   확인한 뒤에만 마일스톤 2(자동 임포트) 진행. 실계좌 전환은 사용자가 명시적으로 승인한 뒤에만.
