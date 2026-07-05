import os

from flask import Flask, flash, redirect, render_template, request, url_for

from stockapp_notion.dividends import add_dividend
from stockapp_notion.logging_config import get_logger
from stockapp_notion.notion_api import get_client
from stockapp_notion.portfolio import list_portfolio_summary, sync_all_portfolios
from stockapp_notion.prices import update_all_prices
from stockapp_notion.stocks import add_stock, find_stock_by_code, list_stocks
from stockapp_notion.transactions import add_transaction

logger = get_logger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)

MARKETS = ["코스피", "코스닥", "나스닥", "NYSE", "기타"]
CURRENCIES = ["KRW", "USD"]


def _title(page: dict, prop: str) -> str:
    items = page["properties"][prop]["title"]
    return items[0]["text"]["content"] if items else ""


def _rich_text(page: dict, prop: str) -> str:
    items = page["properties"][prop]["rich_text"]
    return items[0]["text"]["content"] if items else ""


def _select_name(page: dict, prop: str) -> str:
    select = page["properties"][prop]["select"]
    return select["name"] if select else ""


def _number(page: dict, prop: str) -> float:
    return page["properties"][prop]["number"] or 0


def _stock_rows(client) -> list[dict]:
    rows = []
    for page in list_stocks(client=client):
        rows.append(
            {
                "name": _title(page, "종목명"),
                "code": _rich_text(page, "종목코드"),
                "market": _select_name(page, "시장구분"),
                "sector": _select_name(page, "섹터"),
                "currency": _select_name(page, "통화"),
                "current_price": _number(page, "현재가"),
            }
        )
    return rows


def _portfolio_totals(holdings: list[dict]) -> dict:
    total_valuation = sum(h["valuation"] for h in holdings)
    total_profit = sum(h["profit"] for h in holdings)
    total_cost = total_valuation - total_profit
    total_return_pct = (total_profit / total_cost * 100) if total_cost else 0.0
    return {
        "valuation": total_valuation,
        "profit": total_profit,
        "return_pct": total_return_pct,
    }


@app.route("/")
def index():
    client = get_client()
    stocks = _stock_rows(client)
    holdings = [h for h in list_portfolio_summary(client=client) if h["qty"] > 0]
    totals = _portfolio_totals(holdings)
    return render_template(
        "index.html",
        stocks=stocks,
        markets=MARKETS,
        currencies=CURRENCIES,
        holdings=holdings,
        totals=totals,
    )


@app.route("/stocks", methods=["POST"])
def create_stock():
    try:
        add_stock(
            name=request.form["name"],
            code=request.form["code"],
            market=request.form["market"],
            sector=request.form["sector"],
            currency=request.form["currency"],
        )
        flash(f"종목 등록 완료: {request.form['name']}({request.form['code']})", "success")
    except Exception as exc:
        logger.exception("웹 UI 종목 등록 실패")
        flash(f"종목 등록 실패: {exc}", "error")
    return redirect(url_for("index"))


@app.route("/transactions", methods=["POST"])
def create_transaction():
    code = request.form["code"]
    try:
        client = get_client()
        stock = find_stock_by_code(code, client=client)
        if not stock:
            flash(f"종목코드 {code}를 찾을 수 없습니다. 먼저 종목을 등록하세요.", "error")
            return redirect(url_for("index"))

        add_transaction(
            stock_page_id=stock["id"],
            trade_date=request.form["date"],
            buy_sell=request.form["type"],
            qty=float(request.form["qty"]),
            price=float(request.form["price"]),
            fee=float(request.form.get("fee") or 0),
            client=client,
        )
        sync_all_portfolios(client=client)
        flash(f"매매내역 등록 완료: {code} {request.form['type']} {request.form['qty']}주", "success")
    except Exception as exc:
        logger.exception("웹 UI 매매내역 등록 실패")
        flash(f"매매내역 등록 실패: {exc}", "error")
    return redirect(url_for("index"))


@app.route("/dividends", methods=["POST"])
def create_dividend():
    code = request.form["code"]
    try:
        client = get_client()
        stock = find_stock_by_code(code, client=client)
        if not stock:
            flash(f"종목코드 {code}를 찾을 수 없습니다. 먼저 종목을 등록하세요.", "error")
            return redirect(url_for("index"))

        add_dividend(
            stock_page_id=stock["id"],
            pay_date=request.form["date"],
            pretax_amount=float(request.form["pretax"]),
            posttax_amount=float(request.form["posttax"]),
            client=client,
        )
        flash(f"배당금 등록 완료: {code}", "success")
    except Exception as exc:
        logger.exception("웹 UI 배당금 등록 실패")
        flash(f"배당금 등록 실패: {exc}", "error")
    return redirect(url_for("index"))


@app.route("/actions/update-prices", methods=["POST"])
def action_update_prices():
    try:
        result = update_all_prices()
        flash(f"현재가 갱신 완료: 성공 {result['success']}건, 실패 {result['failed']}건", "success")
    except Exception as exc:
        logger.exception("웹 UI 현재가 갱신 실패")
        flash(f"현재가 갱신 실패: {exc}", "error")
    return redirect(url_for("index"))


@app.route("/actions/sync-portfolio", methods=["POST"])
def action_sync_portfolio():
    try:
        sync_all_portfolios()
        flash("포트폴리오 요약을 재계산했습니다.", "success")
    except Exception as exc:
        logger.exception("웹 UI 포트폴리오 동기화 실패")
        flash(f"포트폴리오 동기화 실패: {exc}", "error")
    return redirect(url_for("index"))


@app.route("/actions/daily-update", methods=["POST"])
def action_daily_update():
    try:
        result = update_all_prices()
        sync_all_portfolios()
        flash(f"일일 갱신 완료: 시세 성공 {result['success']}건, 실패 {result['failed']}건", "success")
    except Exception as exc:
        logger.exception("웹 UI 일일 갱신 실패")
        flash(f"일일 갱신 실패: {exc}", "error")
    return redirect(url_for("index"))


def main() -> None:
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
