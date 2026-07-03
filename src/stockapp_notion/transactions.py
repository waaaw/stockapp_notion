from stockapp_notion.config import settings
from stockapp_notion.logging_config import get_logger
from stockapp_notion.notion_api import call_with_retry, get_client

logger = get_logger(__name__)


def compute_total_amount(buy_sell: str, qty: float, price: float, fee: float) -> float:
    """총거래금액 = 수량×단가±수수료.
    매수는 수수료를 더해 총 지출액을, 매도는 수수료를 빼 실수령액을 나타낸다."""
    base = qty * price
    return base + fee if buy_sell == "매수" else base - fee


def add_transaction(
    stock_page_id: str,
    trade_date: str,
    buy_sell: str,
    qty: float,
    price: float,
    fee: float = 0,
    client=None,
) -> dict:
    if buy_sell not in ("매수", "매도"):
        raise ValueError(f"매매구분은 '매수' 또는 '매도'여야 합니다: {buy_sell}")

    client = client or get_client()
    total_amount = compute_total_amount(buy_sell, qty, price, fee)

    page = call_with_retry(
        client.pages.create,
        parent={"database_id": settings.db_transactions_id},
        properties={
            "거래일자": {"date": {"start": trade_date}},
            "종목": {"relation": [{"id": stock_page_id}]},
            "매매구분": {"select": {"name": buy_sell}},
            "수량": {"number": qty},
            "단가": {"number": price},
            "수수료": {"number": fee},
            "총거래금액": {"number": total_amount},
        },
    )
    logger.info(
        "매매내역 등록: %s %s주 @ %s (수수료 %s, 총액 %s)", buy_sell, qty, price, fee, total_amount
    )
    return page


def list_transactions_for_stock(stock_page_id: str, client=None) -> list[dict]:
    """특정 종목의 전체 매매내역을 페이징 처리하여 거래일자 오름차순으로 반환한다."""
    client = client or get_client()
    results: list[dict] = []
    cursor = None
    while True:
        response = call_with_retry(
            client.databases.query,
            database_id=settings.db_transactions_id,
            filter={"property": "종목", "relation": {"contains": stock_page_id}},
            sorts=[{"property": "거래일자", "direction": "ascending"}],
            start_cursor=cursor,
        )
        results.extend(response["results"])
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")
    return results
