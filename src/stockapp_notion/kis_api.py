"""한국투자증권(KIS) Open API 연동 - 마일스톤 1: 읽기 전용 잔고조회 및 교차검증.

notion_api.py와 같은 구조(인증 헬퍼 + 재시도 래퍼)를 따른다.
이 모듈은 KIS의 조회(read) 엔드포인트만 호출하며, 주문 실행 엔드포인트는 절대 사용하지 않는다.

토큰은 발급 횟수 제한이 있어 디스크(.kis_token_cache.json)에 캐싱한다
(스케줄러가 매일 새 프로세스로 실행되므로 메모리 캐시만으로는 매번 재발급됨).
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

from stockapp_notion.config import settings
from stockapp_notion.logging_config import get_logger

logger = get_logger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_TOKEN_CACHE_PATH = _PROJECT_ROOT / ".kis_token_cache.json"

_MAX_RETRIES = 5
_BASE_DELAY_SECONDS = 1.0
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}

# 주식잔고조회 TR ID (실전/모의). KIS가 개정할 수 있으므로 오류 시 공식 문서 재확인:
# https://apiportal.koreainvestment.com/apiservice
_TR_BALANCE_REAL = "TTTC8434R"
_TR_BALANCE_PAPER = "VTTC8434R"


def _request_with_retry(method: str, url: str, **kwargs) -> dict:
    """HTTP 요청을 429/5xx에 대해 지수 백오프로 재시도한다(notion_api.call_with_retry와 동일 구조)."""
    last_response = None
    for attempt in range(1, _MAX_RETRIES + 1):
        response = requests.request(method, url, timeout=15, **kwargs)
        last_response = response
        if response.status_code in _RETRYABLE_STATUS and attempt < _MAX_RETRIES:
            delay = _BASE_DELAY_SECONDS * (2 ** (attempt - 1))
            logger.warning(
                "KIS API 재시도 %s/%s (HTTP %s) - %.1f초 후 재시도",
                attempt,
                _MAX_RETRIES,
                response.status_code,
                delay,
            )
            time.sleep(delay)
            continue
        break

    if last_response.status_code >= 400:
        logger.error("KIS API 호출 실패: HTTP %s %s", last_response.status_code, last_response.text[:500])
        last_response.raise_for_status()
    return last_response.json()


def _read_token_cache() -> str | None:
    if not _TOKEN_CACHE_PATH.exists():
        return None
    try:
        cache = json.loads(_TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    # 모의/실전 환경이 바뀌면 캐시 무효 (다른 환경용 토큰 재사용 방지)
    if cache.get("is_paper") != settings.kis_is_paper:
        return None
    expires_at = datetime.fromisoformat(cache["expires_at"])
    if datetime.now() >= expires_at - timedelta(hours=1):  # 만료 1시간 전부터 재발급
        return None
    return cache["access_token"]


def get_access_token() -> str:
    """액세스 토큰을 반환한다. 유효한 캐시가 있으면 재사용, 없으면 새로 발급 후 캐싱."""
    cached = _read_token_cache()
    if cached:
        return cached

    body = {
        "grant_type": "client_credentials",
        "appkey": settings.kis_app_key,
        "appsecret": settings.kis_app_secret,
    }
    data = _request_with_retry("POST", f"{settings.kis_base_url}/oauth2/tokenP", json=body)
    token = data["access_token"]
    expires_in = int(data.get("expires_in", 86400))

    _TOKEN_CACHE_PATH.write_text(
        json.dumps(
            {
                "access_token": token,
                "expires_at": (datetime.now() + timedelta(seconds=expires_in)).isoformat(),
                "is_paper": settings.kis_is_paper,
            }
        ),
        encoding="utf-8",
    )
    logger.info("KIS 액세스 토큰 신규 발급 (모의투자: %s, 만료 %s초 후)", settings.kis_is_paper, expires_in)
    return token


def _auth_headers(tr_id: str) -> dict:
    return {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {get_access_token()}",
        "appkey": settings.kis_app_key,
        "appsecret": settings.kis_app_secret,
        "tr_id": tr_id,
    }


def fetch_account_balance() -> list[dict]:
    """주식잔고조회. 보유 종목별 정보를 정규화한 리스트로 반환한다.

    반환 항목: code(종목코드), name(종목명), qty(보유수량), avg_price(매입평균가),
    current_price(현재가), valuation(평가금액), profit(평가손익)
    """
    tr_id = _TR_BALANCE_PAPER if settings.kis_is_paper else _TR_BALANCE_REAL
    account = settings.kis_account_no
    cano, acnt_prdt_cd = account[:8], account[8:10]

    holdings: list[dict] = []
    ctx_fk, ctx_nk = "", ""
    while True:
        params = {
            "CANO": cano,
            "ACNT_PRDT_CD": acnt_prdt_cd,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "00",
            "CTX_AREA_FK100": ctx_fk,
            "CTX_AREA_NK100": ctx_nk,
        }
        data = _request_with_retry(
            "GET",
            f"{settings.kis_base_url}/uapi/domestic-stock/v1/trading/inquire-balance",
            headers=_auth_headers(tr_id),
            params=params,
        )
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"KIS 잔고조회 실패: [{data.get('msg_cd')}] {data.get('msg1')}")

        for row in data.get("output1", []):
            qty = float(row.get("hldg_qty") or 0)
            if qty <= 0:
                continue
            holdings.append(
                {
                    "code": row.get("pdno", ""),
                    "name": row.get("prdt_name", ""),
                    "qty": qty,
                    "avg_price": float(row.get("pchs_avg_pric") or 0),
                    "current_price": float(row.get("prpr") or 0),
                    "valuation": float(row.get("evlu_amt") or 0),
                    "profit": float(row.get("evlu_pfls_amt") or 0),
                }
            )

        # 연속조회: tr_cont가 F/M이면 다음 페이지 존재
        ctx_fk = (data.get("ctx_area_fk100") or "").strip()
        ctx_nk = (data.get("ctx_area_nk100") or "").strip()
        if not ctx_nk:
            break
        time.sleep(0.1)  # 모의투자 환경 호출 제한(초당 2회) 보호

    logger.info("KIS 잔고조회 완료: 보유 %s종목 (모의투자: %s)", len(holdings), settings.kis_is_paper)
    return holdings


def check_balance_against_notion(client=None) -> list[str]:
    """KIS 실제 잔고와 Notion 매매내역 기반 계산 결과를 비교해 불일치 목록을 반환한다.
    아무것도 덮어쓰지 않는다(읽기 전용 교차검증).

    반환: 불일치 설명 문자열 리스트 (비어 있으면 완전 일치)
    """
    from stockapp_notion.portfolio import list_portfolio_summary  # 순환 임포트 방지용 지연 임포트

    kis_holdings = {h["code"]: h for h in fetch_account_balance()}
    notion_holdings = {
        row["code"]: row for row in list_portfolio_summary(client=client) if row["qty"] > 0
    }

    discrepancies: list[str] = []

    for code, kis in kis_holdings.items():
        notion = notion_holdings.get(code)
        if notion is None:
            discrepancies.append(
                f"KIS에만 존재: {kis['name']}({code}) {kis['qty']:.0f}주 - Notion 매매내역에 누락된 매수 기록이 있을 수 있음"
            )
            continue
        if abs(kis["qty"] - notion["qty"]) > 1e-6:
            discrepancies.append(
                f"수량 불일치: {kis['name']}({code}) KIS {kis['qty']:.0f}주 vs Notion {notion['qty']:.0f}주"
            )
        if notion["avg_price"] and abs(kis["avg_price"] - notion["avg_price"]) / notion["avg_price"] > 0.01:
            discrepancies.append(
                f"평균단가 불일치(1% 초과): {kis['name']}({code}) KIS {kis['avg_price']:,.0f} vs Notion {notion['avg_price']:,.0f}"
            )

    for code, notion in notion_holdings.items():
        if code not in kis_holdings:
            discrepancies.append(
                f"Notion에만 존재: {notion['name']}({code}) {notion['qty']:.0f}주 - 실계좌에 없는 종목(수동 관리 종목이면 정상)"
            )

    if discrepancies:
        for d in discrepancies:
            logger.warning("잔고 교차검증: %s", d)
    else:
        logger.info("잔고 교차검증: KIS 계좌와 Notion 기록이 일치합니다 (%s종목)", len(kis_holdings))
    return discrepancies
