from dataclasses import dataclass

from stockapp_notion.config import settings
from stockapp_notion.logging_config import get_logger
from stockapp_notion.notion_api import call_with_retry, get_client, resolve_data_source_id
from stockapp_notion.stocks import list_stocks
from stockapp_notion.transactions import list_transactions_for_stock

logger = get_logger(__name__)


@dataclass
class Holding:
    qty: float
    avg_price: float


def _prop_number(page: dict, name: str) -> float:
    return page["properties"][name]["number"] or 0


def _prop_select_name(page: dict, name: str) -> str:
    select = page["properties"][name]["select"]
    return select["name"] if select else ""


def _prop_title(page: dict, name: str) -> str:
    items = page["properties"][name]["title"]
    return items[0]["text"]["content"] if items else ""


def _prop_rich_text(page: dict, name: str) -> str:
    items = page["properties"][name]["rich_text"]
    return items[0]["text"]["content"] if items else ""


def compute_holding(transactions: list[dict]) -> Holding:
    """거래일자 오름차순 매매내역으로부터 이동평균 방식 보유수량/평균단가를 계산한다.
    매도 시 평균단가는 유지되고 남은 수량만 줄어든다(단순 가중평균 방식)."""
    qty = 0.0
    avg_price = 0.0
    for tx in transactions:
        tx_qty = _prop_number(tx, "수량")
        tx_price = _prop_number(tx, "단가")
        buy_sell = _prop_select_name(tx, "매매구분")

        if buy_sell == "매수":
            new_qty = qty + tx_qty
            if new_qty > 0:
                avg_price = (avg_price * qty + tx_price * tx_qty) / new_qty
            qty = new_qty
        else:  # 매도
            qty -= tx_qty
            if qty <= 0:
                qty = 0.0
                avg_price = 0.0

    return Holding(qty=qty, avg_price=avg_price)


def find_portfolio_page(stock_page_id: str, client=None) -> dict | None:
    client = client or get_client()
    data_source_id = resolve_data_source_id(client, settings.db_portfolio_id)
    response = call_with_retry(
        client.data_sources.query,
        data_source_id=data_source_id,
        filter={"property": "종목", "relation": {"contains": stock_page_id}},
    )
    results = response["results"]
    return results[0] if results else None


def sync_portfolio_for_stock(stock_page: dict, client=None) -> dict | None:
    """한 종목의 매매내역을 집계하여 포트폴리오 요약 DB의 해당 행을 upsert한다.
    보유수량이 0이면 평가 항목을 모두 0으로 기록한다."""
    client = client or get_client()
    stock_page_id = stock_page["id"]
    current_price = _prop_number(stock_page, "현재가")

    transactions = list_transactions_for_stock(stock_page_id, client=client)
    holding = compute_holding(transactions)

    valuation = holding.qty * current_price
    cost_basis = holding.qty * holding.avg_price
    profit = valuation - cost_basis
    return_pct = (profit / cost_basis * 100) if cost_basis else 0.0

    properties = {
        "종목": {"relation": [{"id": stock_page_id}]},
        "보유수량": {"number": holding.qty},
        "평균단가": {"number": holding.avg_price},
        "평가금액": {"number": valuation},
        "평가손익": {"number": profit},
        "수익률(%)": {"number": return_pct},
    }

    existing = find_portfolio_page(stock_page_id, client=client)
    if existing:
        page = call_with_retry(client.pages.update, page_id=existing["id"], properties=properties)
    else:
        page = call_with_retry(
            client.pages.create,
            parent={"database_id": settings.db_portfolio_id},
            properties=properties,
        )

    logger.info(
        "포트폴리오 갱신: %s 보유 %.2f주, 평단 %.2f, 평가손익 %.2f (%.2f%%)",
        stock_page["properties"]["종목명"]["title"][0]["text"]["content"]
        if stock_page["properties"]["종목명"]["title"]
        else stock_page_id,
        holding.qty,
        holding.avg_price,
        profit,
        return_pct,
    )
    return page


def list_portfolio_summary(client=None) -> list[dict]:
    """포트폴리오 요약 DB의 모든 행을 종목명/코드와 함께 정리해 반환한다(웹 UI 보유 현황용).
    평가금액이 큰 순서로 정렬한다."""
    client = client or get_client()
    data_source_id = resolve_data_source_id(client, settings.db_portfolio_id)

    rows: list[dict] = []
    cursor = None
    while True:
        response = call_with_retry(
            client.data_sources.query, data_source_id=data_source_id, start_cursor=cursor
        )
        rows.extend(response["results"])
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")

    stocks_by_id = {page["id"]: page for page in list_stocks(client=client)}

    summary = []
    for row in rows:
        relation = row["properties"]["종목"]["relation"]
        stock_page = stocks_by_id.get(relation[0]["id"]) if relation else None
        summary.append(
            {
                "name": _prop_title(stock_page, "종목명") if stock_page else "(알 수 없음)",
                "code": _prop_rich_text(stock_page, "종목코드") if stock_page else "",
                "qty": _prop_number(row, "보유수량"),
                "avg_price": _prop_number(row, "평균단가"),
                "valuation": _prop_number(row, "평가금액"),
                "profit": _prop_number(row, "평가손익"),
                "return_pct": _prop_number(row, "수익률(%)"),
            }
        )
    summary.sort(key=lambda r: r["valuation"], reverse=True)
    return summary


def sync_all_portfolios(client=None) -> None:
    client = client or get_client()
    stocks = list_stocks(client=client)
    for stock_page in stocks:
        try:
            sync_portfolio_for_stock(stock_page, client=client)
        except Exception:
            name_prop = stock_page["properties"].get("종목명", {}).get("title", [])
            name = name_prop[0]["text"]["content"] if name_prop else stock_page["id"]
            logger.exception("포트폴리오 동기화 실패: %s", name)
