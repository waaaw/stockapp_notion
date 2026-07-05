from stockapp_notion.config import settings
from stockapp_notion.logging_config import get_logger
from stockapp_notion.notion_api import call_with_retry, get_client, resolve_data_source_id
from stockapp_notion.validation import validate_date_str, validate_non_negative, validate_positive

logger = get_logger(__name__)

BUY = "매수"
SELL = "매도"
TRADE_TYPES = (BUY, SELL)


def compute_total_amount(buy_sell: str, qty: float, price: float, fee: float) -> float:
    """총거래금액 = 수량×단가±수수료.
    매수는 수수료를 더해 총 지출액을, 매도는 수수료를 빼 실수령액을 나타낸다."""
    base = qty * price
    return base + fee if buy_sell == BUY else base - fee


def find_duplicate_transaction(
    stock_page_id: str, trade_date: str, buy_sell: str, qty: float, price: float, client=None
) -> dict | None:
    """동일 종목/일자/매매구분/수량/단가의 기존 매매내역이 있는지 확인한다(입력 실수 경고용).
    차단하지 않고 호출자가 경고 표시 여부를 판단하도록 결과만 반환한다."""
    client = client or get_client()
    data_source_id = resolve_data_source_id(client, settings.db_transactions_id)
    response = call_with_retry(
        client.data_sources.query,
        data_source_id=data_source_id,
        filter={
            "and": [
                {"property": "종목", "relation": {"contains": stock_page_id}},
                {"property": "거래일자", "date": {"equals": trade_date}},
                {"property": "매매구분", "select": {"equals": buy_sell}},
                {"property": "수량", "number": {"equals": qty}},
                {"property": "단가", "number": {"equals": price}},
            ]
        },
    )
    results = response["results"]
    return results[0] if results else None


def add_transaction(
    stock_page_id: str,
    trade_date: str,
    buy_sell: str,
    qty: float,
    price: float,
    fee: float = 0,
    client=None,
) -> dict:
    if buy_sell not in TRADE_TYPES:
        raise ValueError(f"매매구분은 '매수' 또는 '매도'여야 합니다: {buy_sell}")
    validate_positive(qty, "수량")
    validate_positive(price, "단가")
    validate_non_negative(fee, "수수료")
    validate_date_str(trade_date)

    client = client or get_client()

    if find_duplicate_transaction(stock_page_id, trade_date, buy_sell, qty, price, client=client):
        logger.warning(
            "동일 조건의 매매내역이 이미 존재합니다 (%s %s %s주 @ %s) - 중복 입력일 수 있으니 확인하세요.",
            trade_date,
            buy_sell,
            qty,
            price,
        )

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


def update_transaction(
    transaction_page_id: str,
    *,
    trade_date: str | None = None,
    buy_sell: str | None = None,
    qty: float | None = None,
    price: float | None = None,
    fee: float | None = None,
    client=None,
) -> dict:
    """매매내역 일부 필드를 수정한다. 수량/단가/매매구분/수수료 중 하나라도 바뀌면 총거래금액도 재계산한다."""
    if buy_sell is not None and buy_sell not in TRADE_TYPES:
        raise ValueError(f"매매구분은 '매수' 또는 '매도'여야 합니다: {buy_sell}")
    if qty is not None:
        validate_positive(qty, "수량")
    if price is not None:
        validate_positive(price, "단가")
    if fee is not None:
        validate_non_negative(fee, "수수료")
    if trade_date is not None:
        validate_date_str(trade_date)

    client = client or get_client()
    page = call_with_retry(client.pages.retrieve, page_id=transaction_page_id)
    props = page["properties"]

    current_buy_sell = buy_sell or props["매매구분"]["select"]["name"]
    current_qty = qty if qty is not None else props["수량"]["number"]
    current_price = price if price is not None else props["단가"]["number"]
    current_fee = fee if fee is not None else props["수수료"]["number"]

    properties: dict = {}
    if trade_date is not None:
        properties["거래일자"] = {"date": {"start": trade_date}}
    if buy_sell is not None:
        properties["매매구분"] = {"select": {"name": buy_sell}}
    if qty is not None:
        properties["수량"] = {"number": qty}
    if price is not None:
        properties["단가"] = {"number": price}
    if fee is not None:
        properties["수수료"] = {"number": fee}
    if qty is not None or price is not None or fee is not None or buy_sell is not None:
        properties["총거래금액"] = {
            "number": compute_total_amount(current_buy_sell, current_qty, current_price, current_fee)
        }

    updated = call_with_retry(client.pages.update, page_id=transaction_page_id, properties=properties)
    logger.info("매매내역 수정: %s", transaction_page_id)
    return updated


def delete_transaction(transaction_page_id: str, client=None) -> None:
    """매매내역을 삭제한다. Notion API는 완전삭제를 지원하지 않아 휴지통으로 이동한다(복구 가능)."""
    client = client or get_client()
    call_with_retry(client.pages.update, page_id=transaction_page_id, archived=True)
    logger.info("매매내역 삭제(휴지통 이동): %s", transaction_page_id)


def list_transactions_for_stock(stock_page_id: str, client=None) -> list[dict]:
    """특정 종목의 전체 매매내역을 페이징 처리하여 거래일자 오름차순으로 반환한다."""
    client = client or get_client()
    data_source_id = resolve_data_source_id(client, settings.db_transactions_id)
    results: list[dict] = []
    cursor = None
    while True:
        response = call_with_retry(
            client.data_sources.query,
            data_source_id=data_source_id,
            filter={"property": "종목", "relation": {"contains": stock_page_id}},
            sorts=[{"property": "거래일자", "direction": "ascending"}],
            start_cursor=cursor,
        )
        results.extend(response["results"])
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")
    return results
