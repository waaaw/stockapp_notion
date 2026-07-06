import os

from flask import Flask, flash, redirect, render_template, request, url_for

from stockapp_notion.dividends import add_dividend
from stockapp_notion.logging_config import get_logger
from stockapp_notion.notion_api import get_client
from stockapp_notion.notion_helpers import prop_number, prop_rich_text, prop_select_name, prop_title
from stockapp_notion.markets import CURRENCIES, MARKETS
from stockapp_notion.portfolio import list_portfolio_summary, sync_all_portfolios, sync_portfolio_for_stock
from stockapp_notion.prices import fetch_fx_rate_to_krw, update_all_prices
from stockapp_notion.stocks import add_stock, find_stock_by_code, list_stocks
from stockapp_notion.transactions import (
    TRADE_TYPES,
    add_transaction,
    delete_transaction,
    find_duplicate_transaction,
    list_transactions_for_stock,
    update_transaction,
)

logger = get_logger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)


def _stock_rows(client) -> list[dict]:
    rows = []
    for page in list_stocks(client=client):
        rows.append(
            {
                "name": prop_title(page, "종목명"),
                "code": prop_rich_text(page, "종목코드"),
                "market": prop_select_name(page, "시장구분"),
                "sector": prop_select_name(page, "섹터"),
                "currency": prop_select_name(page, "통화"),
                "current_price": prop_number(page, "현재가"),
            }
        )
    return rows


_TOTAL_FIELDS = ("valuation", "profit", "realized_pnl", "total_return")


def _sum_group(rows: list[dict]) -> dict:
    agg = {f: sum(r[f] for r in rows) for f in _TOTAL_FIELDS}
    cost = agg["valuation"] - agg["profit"]
    agg["return_pct"] = (agg["profit"] / cost * 100) if cost else 0.0
    return agg


def _portfolio_totals(summary: list[dict]) -> dict:
    """통화가 섞여 있어도 잘못된 합산을 하지 않도록 통화별로 소계를 내고,
    환율을 조회해 KRW 환산 총계도 함께 계산한다. 모든 종목이 KRW면 환율 조회 없이
    기존과 동일하게 동작한다.

    반환:
      by_currency: {통화: {소계 필드...}}  (해당 통화 원화폐 기준)
      krw: {KRW 환산 총계 필드...}
      multi_currency: 통화가 2개 이상인지
      fx_rates: {통화: 환율}
      fx_incomplete: 일부 통화 환율 조회 실패 여부(총계가 불완전할 수 있음)
    """
    by_currency: dict[str, dict] = {}
    for cur in {h["currency"] for h in summary}:
        by_currency[cur] = _sum_group([h for h in summary if h["currency"] == cur])

    # KRW 환산 총계 (KRW은 환율 1.0, 그 외는 yfinance 조회)
    krw = {f: 0.0 for f in _TOTAL_FIELDS}
    fx_rates: dict[str, float] = {}
    fx_incomplete = False
    for cur, sub in by_currency.items():
        rate = fetch_fx_rate_to_krw(cur)
        if rate is None:
            fx_incomplete = True
            continue
        fx_rates[cur] = rate
        for f in _TOTAL_FIELDS:
            krw[f] += sub[f] * rate
    krw_cost = krw["valuation"] - krw["profit"]
    krw["return_pct"] = (krw["profit"] / krw_cost * 100) if krw_cost else 0.0

    return {
        "by_currency": by_currency,
        "krw": krw,
        "multi_currency": len(by_currency) > 1,
        "fx_rates": fx_rates,
        "fx_incomplete": fx_incomplete,
    }


@app.route("/")
def index():
    client = get_client()
    stocks = _stock_rows(client)
    summary = list_portfolio_summary(client=client)
    # 청산(보유수량 0)된 종목도 실현손익/총수익 합계에는 반영하되, 표에는 현재 보유 중인 종목만 보여준다.
    holdings = [h for h in summary if h["qty"] > 0]
    totals = _portfolio_totals(summary)
    # 종목 비중 차트는 통화가 섞여도 공정하게 비교되도록 KRW 환산 평가금액을 쓴다.
    for h in holdings:
        rate = totals["fx_rates"].get(h["currency"], 1.0)
        h["krw_valuation"] = h["valuation"] * rate
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

        trade_date = request.form["date"]
        buy_sell = request.form["type"]
        qty = float(request.form["qty"])
        price = float(request.form["price"])
        if find_duplicate_transaction(stock["id"], trade_date, buy_sell, qty, price, client=client):
            flash(f"주의: 동일 조건({trade_date} {buy_sell} {qty}주 @ {price})의 매매내역이 이미 있습니다. 그래도 등록을 진행합니다.", "error")

        add_transaction(
            stock_page_id=stock["id"],
            trade_date=trade_date,
            buy_sell=buy_sell,
            qty=qty,
            price=price,
            fee=float(request.form.get("fee") or 0),
            client=client,
        )
        sync_all_portfolios(client=client)
        flash(f"매매내역 등록 완료: {code} {buy_sell} {qty}주", "success")
    except Exception as exc:
        logger.exception("웹 UI 매매내역 등록 실패")
        flash(f"매매내역 등록 실패: {exc}", "error")
    return redirect(url_for("index"))


@app.route("/transactions/<code>")
def view_transactions(code):
    client = get_client()
    stock = find_stock_by_code(code, client=client)
    if not stock:
        flash(f"종목코드 {code}를 찾을 수 없습니다.", "error")
        return redirect(url_for("index"))

    rows = []
    for tx in list_transactions_for_stock(stock["id"], client=client):
        props = tx["properties"]
        rows.append(
            {
                "id": tx["id"],
                "trade_date": props["거래일자"]["date"]["start"] if props["거래일자"]["date"] else "",
                "type": props["매매구분"]["select"]["name"] if props["매매구분"]["select"] else "",
                "qty": props["수량"]["number"] or 0,
                "price": props["단가"]["number"] or 0,
                "fee": props["수수료"]["number"] or 0,
                "total_amount": props["총거래금액"]["number"] or 0,
            }
        )
    rows.sort(key=lambda r: r["trade_date"], reverse=True)

    return render_template(
        "transactions.html",
        stock_name=prop_title(stock, "종목명"),
        code=code,
        rows=rows,
        trade_types=TRADE_TYPES,
    )


@app.route("/transactions/<transaction_id>/edit", methods=["POST"])
def edit_transaction(transaction_id):
    code = request.form["code"]
    try:
        client = get_client()
        tx = client.pages.retrieve(page_id=transaction_id)
        stock_id = tx["properties"]["종목"]["relation"][0]["id"]

        update_transaction(
            transaction_id,
            trade_date=request.form["date"] or None,
            buy_sell=request.form["type"] or None,
            qty=float(request.form["qty"]) if request.form.get("qty") else None,
            price=float(request.form["price"]) if request.form.get("price") else None,
            fee=float(request.form["fee"]) if request.form.get("fee") else None,
            client=client,
        )
        stock = client.pages.retrieve(page_id=stock_id)
        sync_portfolio_for_stock(stock, client=client)
        flash("매매내역을 수정했습니다.", "success")
    except Exception as exc:
        logger.exception("웹 UI 매매내역 수정 실패")
        flash(f"매매내역 수정 실패: {exc}", "error")
    return redirect(url_for("view_transactions", code=code))


@app.route("/transactions/<transaction_id>/delete", methods=["POST"])
def remove_transaction(transaction_id):
    code = request.form["code"]
    try:
        client = get_client()
        tx = client.pages.retrieve(page_id=transaction_id)
        stock_id = tx["properties"]["종목"]["relation"][0]["id"]

        delete_transaction(transaction_id, client=client)
        stock = client.pages.retrieve(page_id=stock_id)
        sync_portfolio_for_stock(stock, client=client)
        flash("매매내역을 삭제했습니다.", "success")
    except Exception as exc:
        logger.exception("웹 UI 매매내역 삭제 실패")
        flash(f"매매내역 삭제 실패: {exc}", "error")
    return redirect(url_for("view_transactions", code=code))


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
