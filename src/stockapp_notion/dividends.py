from stockapp_notion.config import settings
from stockapp_notion.logging_config import get_logger
from stockapp_notion.notion_api import call_with_retry, get_client

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
