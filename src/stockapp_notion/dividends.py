from stockapp_notion.config import settings
from stockapp_notion.logging_config import get_logger
from stockapp_notion.notion_api import call_with_retry, get_client, resolve_data_source_id
from stockapp_notion.notion_helpers import prop_number

logger = get_logger(__name__)


def add_dividend(
    stock_page_id: str,
    pay_date: str,
    pretax_amount: float,
    posttax_amount: float,
    client=None,
) -> dict:
    if not settings.db_dividends_id:
        raise RuntimeError("DB_DIVIDENDS_ID가 설정되지 않았습니다. 배당금 DB는 선택 기능입니다.")

    client = client or get_client()
    page = call_with_retry(
        client.pages.create,
        parent={"database_id": settings.db_dividends_id},
        properties={
            "지급일": {"date": {"start": pay_date}},
            "종목": {"relation": [{"id": stock_page_id}]},
            "세전배당금": {"number": pretax_amount},
            "세후배당금": {"number": posttax_amount},
        },
    )
    logger.info("배당금 등록: 세전 %s / 세후 %s (%s)", pretax_amount, posttax_amount, pay_date)
    return page


def total_dividends_for_stock(stock_page_id: str, client=None) -> float:
    """특정 종목의 누적 세후배당금 합계를 반환한다. 배당금 DB가 설정되지 않았으면 0을 반환한다
    (선택 기능이므로 총수익 계산이 이 기능 없이도 동작해야 한다)."""
    if not settings.db_dividends_id:
        return 0.0

    client = client or get_client()
    data_source_id = resolve_data_source_id(client, settings.db_dividends_id)

    total = 0.0
    cursor = None
    while True:
        response = call_with_retry(
            client.data_sources.query,
            data_source_id=data_source_id,
            filter={"property": "종목", "relation": {"contains": stock_page_id}},
            start_cursor=cursor,
        )
        total += sum(prop_number(page, "세후배당금") for page in response["results"])
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")
    return total
