from stockapp_notion.config import settings
from stockapp_notion.logging_config import get_logger
from stockapp_notion.markets import ticker_suffix
from stockapp_notion.notion_api import call_with_retry, get_client, resolve_data_source_id
from stockapp_notion.validation import validate_non_empty

logger = get_logger(__name__)


def yfinance_ticker(code: str, market: str) -> str:
    """종목코드+시장구분으로 yfinance 조회용 티커를 만든다.
    국내: 코스피=.KS/코스닥=.KQ, 미국(나스닥/NYSE/AMEX): 코드 그대로,
    중국: 상해=.SS/심천=.SZ, 홍콩=.HK (markets.MARKET_INFO 참조)."""
    return f"{code}{ticker_suffix(market)}"


def list_stocks(client=None) -> list[dict]:
    """종목 마스터 DB의 모든 페이지를 페이징 처리하여 반환한다."""
    client = client or get_client()
    data_source_id = resolve_data_source_id(client, settings.db_stocks_id)
    results: list[dict] = []
    cursor = None
    while True:
        response = call_with_retry(
            client.data_sources.query,
            data_source_id=data_source_id,
            start_cursor=cursor,
        )
        results.extend(response["results"])
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")
    return results


def find_stock_by_code(code: str, client=None) -> dict | None:
    client = client or get_client()
    data_source_id = resolve_data_source_id(client, settings.db_stocks_id)
    response = call_with_retry(
        client.data_sources.query,
        data_source_id=data_source_id,
        filter={"property": "종목코드", "rich_text": {"equals": code}},
    )
    results = response["results"]
    return results[0] if results else None


def add_stock(
    name: str,
    code: str,
    market: str,
    sector: str,
    currency: str,
    current_price: float | None = None,
    client=None,
) -> dict:
    """종목 마스터 DB에 신규 종목을 등록한다. 이미 존재하면 등록을 건너뛴다."""
    validate_non_empty(name, "종목명")
    validate_non_empty(code, "종목코드")
    client = client or get_client()

    existing = find_stock_by_code(code, client=client)
    if existing:
        logger.info("종목 %s(%s)는 이미 등록되어 있습니다. 건너뜁니다.", name, code)
        return existing

    properties = {
        "종목명": {"title": [{"text": {"content": name}}]},
        "종목코드": {"rich_text": [{"text": {"content": code}}]},
        "시장구분": {"select": {"name": market}},
        "섹터": {"select": {"name": sector}},
        "통화": {"select": {"name": currency}},
    }
    if current_price is not None:
        properties["현재가"] = {"number": current_price}

    page = call_with_retry(
        client.pages.create,
        parent={"database_id": settings.db_stocks_id},
        properties=properties,
    )
    logger.info("종목 등록 완료: %s(%s)", name, code)
    return page
