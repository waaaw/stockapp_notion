"""시장구분/통화 상수와 yfinance 티커 매핑을 한 곳에 모은다.
cli.py, webapp.py, stocks.py, prices.py, setup_notion_databases.py가 모두 이 정의를 공유해
시장/통화 옵션이 파일마다 어긋나지 않게 한다."""

# 시장구분 -> (yfinance 티커 접미사, 기본 통화)
# 미국(나스닥/NYSE/AMEX)은 티커를 그대로 사용, 중국은 상해=.SS/심천=.SZ, 홍콩=.HK
MARKET_INFO: dict[str, dict[str, str]] = {
    "코스피": {"suffix": ".KS", "currency": "KRW"},
    "코스닥": {"suffix": ".KQ", "currency": "KRW"},
    "나스닥": {"suffix": "", "currency": "USD"},
    "NYSE": {"suffix": "", "currency": "USD"},
    "AMEX": {"suffix": "", "currency": "USD"},
    "상해": {"suffix": ".SS", "currency": "CNY"},
    "심천": {"suffix": ".SZ", "currency": "CNY"},
    "홍콩": {"suffix": ".HK", "currency": "HKD"},
    "기타": {"suffix": "", "currency": "KRW"},
}

MARKETS: list[str] = list(MARKET_INFO.keys())
CURRENCIES: list[str] = ["KRW", "USD", "CNY", "HKD"]

# 통화 표시용 기호/자릿수 (해외주식은 소수점 둘째 자리까지 의미가 있음)
CURRENCY_FORMAT: dict[str, dict] = {
    "KRW": {"symbol": "₩", "decimals": 0},
    "USD": {"symbol": "$", "decimals": 2},
    "CNY": {"symbol": "¥", "decimals": 2},
    "HKD": {"symbol": "HK$", "decimals": 2},
}


def ticker_suffix(market: str) -> str:
    return MARKET_INFO.get(market, {}).get("suffix", "")


def default_currency(market: str) -> str:
    """시장구분으로부터 기본 통화를 추론한다(폼에서 통화 미지정 시 사용)."""
    return MARKET_INFO.get(market, {}).get("currency", "KRW")
