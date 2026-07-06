# 개선 계획: 전체 점검 후 리팩터링/버그 수정 (2026-07-06)

지금까지의 작업을 처음부터 점검해 발견한 개선점과, 이번에 실제로 적용할 항목을 정리한다.

## 점검으로 발견한 문제

### 정합성/효율 (수정 대상)
1. **재계산 경로 불일치**: 매매내역 *추가*(cli `cmd_add_transaction`, webapp `create_transaction`)는
   `sync_all_portfolios()`로 전 종목을 재계산하는데, *수정/삭제*는 해당 종목만
   `sync_portfolio_for_stock()`으로 재계산한다. 추가 시에도 이미 종목을 알고 있으므로 단일 종목만
   재계산하면 된다(API 호출 수 감소, 일관성).
2. **중복 검사 2회 실행**: webapp `create_transaction`이 `find_duplicate_transaction`을 호출해
   flash를 띄우고, `add_transaction`이 내부에서 또 한 번 호출한다(쿼리 2회). 중복 검사를 호출자
   책임으로 일원화한다.
3. **고아 매매내역 IndexError 위험**: cli/webapp의 수정·삭제·조회에서
   `tx["properties"]["종목"]["relation"][0]["id"]`를 직접 인덱싱한다. 종목 연결이 끊긴 거래가 있으면
   IndexError로 죽는다. 명확한 에러 메시지로 감싼다.

### 죽은 코드/미사용 유틸 (연결)
4. **`markets.default_currency` 미사용**: 종목 등록 폼에서 시장구분을 고르면 통화가 자동 선택되도록
   연결한다(JS + webapp 기본값). UX 개선 + 죽은 코드 제거.
5. **`validation.validate_non_empty` 미사용**: `add_stock`에서 종목명/종목코드 공백 검증에 사용한다.

### UX/견고성
6. **신규 종목 현재가 0 문제**: 종목 등록 직후 현재가가 0으로 남아 다음 배치 전까지 평가금액이
   0으로 보인다. 등록 시 해당 종목 시세를 한 번 즉시 조회해 채운다(실패해도 등록은 성공).
7. **중복 경고가 빨간 error 스타일**: "그래도 진행합니다" 경고인데 error(빨강)로 표시된다. warning
   (노랑) 카테고리를 추가해 구분한다.

### 테스트 가능성
8. **다중통화 집계 로직에 테스트 없음**: `webapp._portfolio_totals`가 네트워크(FX)를 직접 호출해
   테스트가 어렵다. 순수 집계 로직을 `portfolio.aggregate_totals(summary, fx_rate_fn)`로 옮기고
   (Flask 비의존) FX 함수를 주입 가능하게 만들어 단위테스트를 추가한다.

### 이번에 손대지 않는 것 (근거)
- Flask `secret_key = os.urandom(24)` 재시작 시 flash 유실: 1인 로컬 도구라 영향 미미. 1줄 수정이라
  묶어서 처리(환경변수 우선, 없으면 랜덤).
- FX 페이지로드마다 조회: 현재 KRW 단일 통화라 호출 자체가 없음. 주입형으로 바꿔두면 나중에
  캐싱을 쉽게 붙일 수 있어 지금은 구조만 마련.
- 인크리멘털 동기화/배치 최적화, 히스토리 스냅샷: 데이터량이 작아 후순위 유지.

## 적용 항목 (이번 커밋)
1 재계산 단일화 · 2 중복검사 일원화 · 3 고아거래 가드 · 4 통화 자동선택 · 5 종목명/코드 검증 ·
6 등록 시 시세 즉시 조회 · 7 warning 스타일 · 8 집계 로직 분리+테스트 · (묶음) secret_key 환경변수화

## 변경 파일
- `transactions.py`: 내부 중복검사 제거, `stock_id_from_transaction` 헬퍼 추가
- `portfolio.py`: `aggregate_totals(summary, fx_rate_fn)` 추가
- `prices.py`: `refresh_price_for_page(page, client)` 추가(단일 종목 시세 갱신)
- `stocks.py`: `add_stock`에 종목명/코드 공백 검증
- `webapp.py`: 추가 경로 단일 종목 재계산, 중복검사 일원화+warning, 등록 시 시세 조회,
  통화 기본값, `aggregate_totals` 사용, secret_key 환경변수화
- `cli.py`: 추가 경로 단일 종목 재계산, 고아거래 가드
- `templates/index.html`: 시장→통화 자동선택 JS, warning flash 스타일
- `tests/test_reporting.py` (신규): `aggregate_totals` 다중통화 단위테스트

## 검증 (완료)
- `pytest tests/` 18개 전체 통과(기존 14 + 신규 `test_reporting.py` 집계 4개)
- 웹 재기동 후 KRW 단일통화 페이지 회귀 없음(총 평가금액 3,095,000, 통화별 소계 미노출)
- `refresh_price_for_page` 실동작 확인(삼성전자 318,000원 조회·갱신)
- 통화 자동선택 JS 렌더 확인, webapp에 제거한 헬퍼 잔재 없음

## 적용 완료
전 항목 적용 완료(재계산 단일화, 중복검사 일원화, 고아거래 가드, 통화 자동선택, 종목명/코드 검증,
등록 시 시세 즉시 조회, warning 스타일, `aggregate_totals` 분리+테스트, secret_key 환경변수화).
