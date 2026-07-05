from dataclasses import dataclass

from stockapp_notion.config import settings
from stockapp_notion.dividends import total_dividends_for_stock
from stockapp_notion.logging_config import get_logger
from stockapp_notion.notion_api import call_with_retry, ensure_property, get_client, resolve_data_source_id
from stockapp_notion.notion_helpers import prop_number, prop_rich_text, prop_select_name, prop_title
from stockapp_notion.stocks import list_stocks
from stockapp_notion.transactions import BUY, list_transactions_for_stock

logger = get_logger(__name__)

_portfolio_properties_ensured: set[str] = set()


def _ensure_portfolio_properties(client, data_source_id: str) -> None:
    """포트폴리오 요약 data source에 누적실현손익/총수익 관련 속성이 없으면 추가한다.
    프로세스당 한 번만 확인하도록 캐싱한다."""
    if data_source_id in _portfolio_properties_ensured:
        return
    ensure_property(client, data_source_id, "누적실현손익", {"number": {"format": "number"}})
    ensure_property(client, data_source_id, "총수익(배당포함)", {"number": {"format": "number"}})
    ensure_property(client, data_source_id, "총수익률(%)", {"number": {"format": "number"}})
    _portfolio_properties_ensured.add(data_source_id)


@dataclass
class Holding:
    qty: float
    avg_price: float


@dataclass
class RealizedGain:
    trade_date: str
    qty: float
    sell_price: float
    avg_cost_at_sale: float
    fee: float
    realized_pnl: float


def _replay_transactions(transactions: list[dict]) -> tuple[Holding, list[RealizedGain]]:
    """거래일자 오름차순 매매내역을 한 번 순회하며 보유수량/평균단가와 매도 건별
    실현손익을 동시에 계산한다(이동 가중평균 방식). 매도 시 평균단가는 유지되고
    남은 수량만 줄어든다."""
    qty = 0.0
    avg_price = 0.0
    realized_gains: list[RealizedGain] = []

    for tx in transactions:
        tx_qty = prop_number(tx, "수량")
        tx_price = prop_number(tx, "단가")
        tx_fee = prop_number(tx, "수수료")
        buy_sell = prop_select_name(tx, "매매구분")
        trade_date = tx["properties"]["거래일자"]["date"]["start"] if tx["properties"]["거래일자"]["date"] else ""

        if buy_sell == BUY:
            new_qty = qty + tx_qty
            if new_qty > 0:
                avg_price = (avg_price * qty + tx_price * tx_qty) / new_qty
            qty = new_qty
        else:  # 매도
            realized_pnl = (tx_price - avg_price) * tx_qty - tx_fee
            realized_gains.append(
                RealizedGain(
                    trade_date=trade_date,
                    qty=tx_qty,
                    sell_price=tx_price,
                    avg_cost_at_sale=avg_price,
                    fee=tx_fee,
                    realized_pnl=realized_pnl,
                )
            )
            qty -= tx_qty
            if qty <= 0:
                qty = 0.0
                avg_price = 0.0

    return Holding(qty=qty, avg_price=avg_price), realized_gains


def compute_holding(transactions: list[dict]) -> Holding:
    """거래일자 오름차순 매매내역으로부터 이동평균 방식 보유수량/평균단가를 계산한다."""
    holding, _ = _replay_transactions(transactions)
    return holding


def compute_realized_gains(transactions: list[dict]) -> list[RealizedGain]:
    """매도 건별 실현손익 목록을 계산한다(매도 시점의 평균단가 기준)."""
    _, realized_gains = _replay_transactions(transactions)
    return realized_gains


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
    보유수량이 0이면 평가 항목을 모두 0으로 기록한다. 누적실현손익과, 있다면 배당금까지
    더한 총수익/총수익률도 함께 기록한다."""
    client = client or get_client()
    stock_page_id = stock_page["id"]
    current_price = prop_number(stock_page, "현재가")

    transactions = list_transactions_for_stock(stock_page_id, client=client)
    holding, realized_gains = _replay_transactions(transactions)
    cumulative_realized = sum(rg.realized_pnl for rg in realized_gains)
    cumulative_dividends = total_dividends_for_stock(stock_page_id, client=client)

    valuation = holding.qty * current_price
    cost_basis = holding.qty * holding.avg_price
    profit = valuation - cost_basis
    return_pct = (profit / cost_basis * 100) if cost_basis else 0.0

    total_return = profit + cumulative_realized + cumulative_dividends
    # 원금 기준 분모: 현재 보유 원가 + 이미 실현된 매도 건의 원가(대략치로 매도가-실현손익 사용)
    total_cost_basis = cost_basis + sum(
        rg.avg_cost_at_sale * rg.qty for rg in realized_gains
    )
    total_return_pct = (total_return / total_cost_basis * 100) if total_cost_basis else 0.0

    portfolio_data_source_id = resolve_data_source_id(client, settings.db_portfolio_id)
    _ensure_portfolio_properties(client, portfolio_data_source_id)

    properties = {
        "종목": {"relation": [{"id": stock_page_id}]},
        "보유수량": {"number": holding.qty},
        "평균단가": {"number": holding.avg_price},
        "평가금액": {"number": valuation},
        "평가손익": {"number": profit},
        "수익률(%)": {"number": return_pct},
        "누적실현손익": {"number": cumulative_realized},
        "총수익(배당포함)": {"number": total_return},
        "총수익률(%)": {"number": total_return_pct},
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
        "포트폴리오 갱신: %s 보유 %.2f주, 평단 %.2f, 평가손익 %.2f (%.2f%%), 총수익 %.2f (%.2f%%)",
        prop_title(stock_page, "종목명") or stock_page_id,
        holding.qty,
        holding.avg_price,
        profit,
        return_pct,
        total_return,
        total_return_pct,
    )
    return page


def list_portfolio_summary(client=None) -> list[dict]:
    """포트폴리오 요약 DB의 모든 행을 종목명/코드와 함께 정리해 반환한다(웹 UI 보유 현황용).
    평가금액이 큰 순서로 정렬한다."""
    client = client or get_client()
    data_source_id = resolve_data_source_id(client, settings.db_portfolio_id)
    _ensure_portfolio_properties(client, data_source_id)

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
                "name": prop_title(stock_page, "종목명") if stock_page else "(알 수 없음)",
                "code": prop_rich_text(stock_page, "종목코드") if stock_page else "",
                "qty": prop_number(row, "보유수량"),
                "avg_price": prop_number(row, "평균단가"),
                "valuation": prop_number(row, "평가금액"),
                "profit": prop_number(row, "평가손익"),
                "return_pct": prop_number(row, "수익률(%)"),
                "realized_pnl": prop_number(row, "누적실현손익"),
                "total_return": prop_number(row, "총수익(배당포함)"),
                "total_return_pct": prop_number(row, "총수익률(%)"),
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
            name = prop_title(stock_page, "종목명") or stock_page["id"]
            logger.exception("포트폴리오 동기화 실패: %s", name)
