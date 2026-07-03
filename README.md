# Notion 기반 주식 포트폴리오 관리 시스템

작업지시서(v1.0, 2026-07-03) 기반으로 구현한 Python + Notion API 연동 프로그램.

## 설계상 결정 사항 (작업지시서 9. 미결정 사항에 대한 기본값)

작업지시서에 명시된 미결정 사항은 아래와 같이 기본값을 정해 진행했습니다. 요구사항이 다르면 관련 절을 수정하세요.

1. **국내/해외 종목**: 둘 다 지원. `yfinance`로 통일하고, 종목의 `시장구분`(코스피=`.KS`, 코스닥=`.KQ`, 나스닥/NYSE=코드 그대로)에 따라 티커를 자동 매핑합니다(`src/stockapp_notion/stocks.py`의 `yfinance_ticker`). 한국투자증권 Open API 실시간 시세가 필요하면 `prices.py`의 `fetch_current_price`만 교체하면 됩니다.
2. **시세 갱신 주기**: 기본은 일 1회 배치(`daily-update` 명령). 수동 실행(`update-prices`)도 항상 가능합니다.
3. **알림 기능(Slack/Telegram)**: Phase 3 범위로 이번 구현에는 포함하지 않았습니다. `prices.py`/`portfolio.py`의 결과 딕셔너리를 훅으로 삼아 추후 추가하기 쉬운 구조입니다.
4. **매매 내역 수기 입력 여부**: Notion DB 자체이므로 Notion 앱/웹에서 언제든 수동 입력 가능하며, CLI(`add-transaction`)로 API 입력도 병행할 수 있습니다. 단, 수기로 입력한 거래는 `sync-portfolio`를 실행해야 포트폴리오 요약에 반영됩니다.

또한 작업지시서는 `평가금액/평가손익/수익률`을 Notion **Formula/Rollup**으로 제안했지만, Formula/Rollup은 Notion API로 생성할 수 없어 UI에서 수작업으로 설정해야 합니다. 대신 이 프로젝트는 **Python이 직접 계산해서 Number 값으로 기록**하는 방식을 택했습니다(`portfolio.py`). 자동화 관점에서 더 안정적이고, DB 속성 생성도 스크립트 한 번으로 끝낼 수 있습니다. `총거래금액`도 동일한 이유로 Python이 계산합니다.

평균단가 계산은 **이동 가중평균 방식**입니다(FIFO 아님). 매도 시 평균단가는 유지된 채 수량만 줄어듭니다.

## 참고: Notion API "Data Source" 구조 (2025-09 API 변경)

`notion-client` 3.x부터는 Notion의 2025-09 API 변경을 반영해 데이터베이스가 하나 이상의
**data source**를 담는 컨테이너로 바뀌었습니다. 실무적으로 영향받는 부분:

- 조회(`query`)는 더 이상 `client.databases.query(database_id=...)`가 아니라
  `client.data_sources.query(data_source_id=...)`를 사용해야 합니다.
- 새 DB를 만들 때 속성 스키마는 `properties`가 아니라 `initial_data_source.properties`로 전달합니다.
- relation 속성은 대상 `database_id`가 아니라 `data_source_id`를 참조해야 합니다.
- 페이지 생성(`pages.create`)의 `parent`는 `{"database_id": ...}`를 계속 써도 동작합니다(하위 호환).

이 프로젝트는 `.env`에는 기존처럼 `database_id`만 저장하고, `notion_api.resolve_data_source_id()`가
내부적으로 `database_id -> data_source_id`를 조회해 캐싱합니다. 즉 `.env` 형식이나 사용자 커맨드는
바뀌지 않고, 라이브러리 레벨의 차이만 흡수합니다.

또한 `yfinance`의 `Ticker(...).fast_info`는 dict처럼 보이지만 `.get("last_price")`로는 값을
가져올 수 없고(`None` 반환), `info.last_price` 속성 접근을 사용해야 합니다(`prices.py`에 반영됨).

## 준비물

- Notion 계정 및 워크스페이스
- Python 3.10+
- [notion.so/my-integrations](https://www.notion.so/my-integrations)에서 Integration 생성 후 토큰 발급
- DB를 생성할 상위 Notion 페이지를 하나 만들고, 해당 Integration과 공유(Connect)

## 설치

```bash
cd stockapp_notion
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
cp .env.example .env
```

`.env`에 `NOTION_TOKEN`을 채워 넣습니다. (DB ID들은 다음 단계에서 채웁니다.)

## 1단계: Notion 데이터베이스 생성

```bash
python scripts/setup_notion_databases.py <상위_페이지_ID>
```

- `<상위_페이지_ID>`는 Integration과 공유된 Notion 페이지 URL 마지막의 32자리 ID입니다.
- 실행하면 종목 마스터/매매 내역/포트폴리오 요약/배당금 내역 4개 DB가 생성되고, 각 `database_id`가 출력됩니다.
- 출력된 4줄(`DB_STOCKS_ID=...` 등)을 `.env`에 복사해 넣으세요.

이미 Notion에서 직접 DB를 만들어 둔 경우, 위 스크립트를 생략하고 각 DB 속성명이 작업지시서/이 README와 동일하게 맞춰져 있는지만 확인한 뒤 `database_id`를 `.env`에 채우면 됩니다.

## 2단계: 종목 등록 및 매매 입력

```bash
# 종목 등록
python -m stockapp_notion.cli add-stock --name 삼성전자 --code 005930 --market 코스피 --sector IT --currency KRW

# 매매내역 입력 (자동으로 포트폴리오 요약도 재계산됨)
python -m stockapp_notion.cli add-transaction --code 005930 --type 매수 --qty 10 --price 70000 --fee 100 --date 2026-07-03

# 배당금 입력 (선택, DB_DIVIDENDS_ID 설정 시)
python -m stockapp_notion.cli add-dividend --code 005930 --date 2026-07-01 --pretax 5000 --posttax 4230
```

## 3단계: 현재가 갱신 및 포트폴리오 동기화

```bash
# 전 종목 현재가 갱신
python -m stockapp_notion.cli update-prices

# 포트폴리오 요약 재계산만 별도 실행
python -m stockapp_notion.cli sync-portfolio

# 위 둘을 한 번에 (cron/스케줄러용)
python -m stockapp_notion.cli daily-update
```

## 4단계: 자동 스케줄링

### cron (Linux, 매일 16:00)

```cron
0 16 * * 1-5 cd /path/to/stockapp_notion && .venv/bin/python -m stockapp_notion.cli daily-update >> logs/cron.log 2>&1
```

### APScheduler (상시 실행 프로세스)

```bash
python scripts/run_daily_update.py
```

## 로깅 및 에러 처리

- 모든 실행 로그는 `logs/app.log`(로테이션, 5개 x 2MB)와 콘솔에 동시 기록됩니다.
- Notion API는 초당 3회 제한이 있어, `notion_api.call_with_retry`가 `rate_limited` 등 재시도 가능한 오류를 지수 백오프(최대 5회)로 재시도합니다.
- 시세 조회 실패, 포트폴리오 동기화 실패는 종목 단위로 캐치되어 다른 종목 처리에 영향을 주지 않고 로그에 실패 건수로 집계됩니다.

## 테스트

```bash
pip install pytest
pytest
```

`tests/test_portfolio.py`는 Notion API 호출 없이 평균단가/보유수량/총거래금액 계산 로직만 검증합니다.

## 프로젝트 구조

```
stockapp_notion/
├── src/stockapp_notion/
│   ├── config.py           # .env 기반 설정
│   ├── logging_config.py   # 로테이팅 파일 로거
│   ├── notion_api.py       # 재시도/백오프 포함 Notion 클라이언트 래퍼
│   ├── stocks.py           # 종목 마스터 CRUD, yfinance 티커 매핑
│   ├── transactions.py     # 매매내역 등록/조회, 총거래금액 계산
│   ├── portfolio.py        # 보유수량/평균단가/평가손익/수익률 계산 및 upsert
│   ├── prices.py           # yfinance 현재가 조회 및 일괄 갱신
│   ├── dividends.py        # 배당금 내역 등록
│   └── cli.py               # CLI 진입점
├── scripts/
│   ├── setup_notion_databases.py  # DB 4개 최초 생성
│   └── run_daily_update.py        # APScheduler 상시 실행 예시
├── tests/test_portfolio.py
└── .env.example
```

## 남은 작업 (Phase 3, 선택)

- 목표 수익률/손절가 알림 (Slack/Telegram webhook)
- 섹터별/자산별 비중 리포트
- 일별/월별 포트폴리오 스냅샷 히스토리 DB
