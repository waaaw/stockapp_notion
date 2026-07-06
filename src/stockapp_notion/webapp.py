import os

from flask import Flask, flash, redirect, render_template, request, session, url_for

from stockapp_notion.auth import check_credentials, is_authenticated, mark_authenticated
from stockapp_notion.config import settings
from stockapp_notion.dividends import add_dividend
from stockapp_notion.logging_config import get_logger
from stockapp_notion.notion_api import get_client
from stockapp_notion.notion_helpers import prop_number, prop_rich_text, prop_select_name, prop_title
from stockapp_notion.markets import CURRENCIES, MARKETS, default_currency
from stockapp_notion.portfolio import (
    aggregate_totals,
    list_portfolio_summary,
    sync_all_portfolios,
    sync_portfolio_for_stock,
)
from stockapp_notion.prices import fetch_fx_rate_to_krw, refresh_price_for_page, update_all_prices
from stockapp_notion.stocks import add_stock, find_stock_by_code, list_stocks
from stockapp_notion.transactions import (
    TRADE_TYPES,
    add_transaction,
    delete_transaction,
    find_duplicate_transaction,
    list_transactions_for_stock,
    stock_id_from_transaction,
    update_transaction,
)

logger = get_logger(__name__)

app = Flask(__name__)

# 로그인을 켤 때는 FLASK_SECRET_KEY가 반드시 있어야 한다. 없으면 gunicorn 다중 워커가
# 각자 다른 임시 키를 만들어 세션 쿠키가 워커마다 무효가 되고 로그인이 간헐적으로 풀린다.
if settings.web_auth_enabled and not os.getenv("FLASK_SECRET_KEY"):
    raise RuntimeError(
        "로그인(WEB_USERNAME/WEB_PASSWORD)을 켜려면 FLASK_SECRET_KEY도 .env에 설정해야 합니다. "
        "(멀티 워커 환경에서 세션이 깨지는 것을 방지)"
    )
# 재시작/멀티 워커 간에도 세션이 유지되도록 환경변수 우선(로컬 무인증 사용 시엔 임시 랜덤 키 허용)
app.secret_key = os.getenv("FLASK_SECRET_KEY") or os.urandom(24)
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

# 로그인 없이 접근 가능한 엔드포인트(로그인 화면, 정적 리소스, 헬스체크)
_PUBLIC_ENDPOINTS = {"login", "static", "health"}


@app.before_request
def _require_login():
    """WEB_USERNAME/WEB_PASSWORD가 .env에 설정된 경우에만 로그인을 강제한다.
    설정 안 되어 있으면(로컬 전용 사용) 기존처럼 인증 없이 동작한다."""
    if not settings.web_auth_enabled:
        return None
    if request.endpoint in _PUBLIC_ENDPOINTS:
        return None
    if not is_authenticated():
        return redirect(url_for("login", next=request.path))
    return None


@app.route("/health")
def health():
    """컨테이너 헬스체크/모니터링용. 인증 없이 200을 반환한다(외부 의존성 조회 안 함)."""
    return {"status": "ok"}, 200


@app.route("/login", methods=["GET", "POST"])
def login():
    if not settings.web_auth_enabled:
        return redirect(url_for("index"))
    if request.method == "POST":
        if check_credentials(request.form.get("username", ""), request.form.get("password", "")):
            mark_authenticated()
            return redirect(request.args.get("next") or url_for("index"))
        flash("아이디 또는 비밀번호가 올바르지 않습니다.", "error")
    return render_template("login.html")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.context_processor
def _inject_auth_flag():
    return {"web_auth_enabled": settings.web_auth_enabled}


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


@app.route("/")
def index():
    client = get_client()
    stocks = _stock_rows(client)
    summary = list_portfolio_summary(client=client)
    # 청산(보유수량 0)된 종목도 실현손익/총수익 합계에는 반영하되, 표에는 현재 보유 중인 종목만 보여준다.
    holdings = [h for h in summary if h["qty"] > 0]
    totals = aggregate_totals(summary, fetch_fx_rate_to_krw)
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
        client = get_client()
        market = request.form["market"]
        # 통화 미선택 시 시장구분으로부터 기본 통화 추론
        currency = request.form.get("currency") or default_currency(market)
        page = add_stock(
            name=request.form["name"],
            code=request.form["code"],
            market=market,
            sector=request.form["sector"],
            currency=currency,
            client=client,
        )
        price = refresh_price_for_page(page, client=client)
        note = f" (현재가 {price:,.0f})" if price is not None else " (현재가 조회 실패 - 나중에 '현재가 갱신')"
        flash(f"종목 등록 완료: {request.form['name']}({request.form['code']}){note}", "success")
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
            flash(f"주의: 동일 조건({trade_date} {buy_sell} {qty}주 @ {price})의 매매내역이 이미 있습니다. 그래도 등록을 진행합니다.", "warning")

        add_transaction(
            stock_page_id=stock["id"],
            trade_date=trade_date,
            buy_sell=buy_sell,
            qty=qty,
            price=price,
            fee=float(request.form.get("fee") or 0),
            client=client,
        )
        sync_portfolio_for_stock(stock, client=client)
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
        stock_id = stock_id_from_transaction(tx)

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
        stock_id = stock_id_from_transaction(tx)

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
    app.run(host=settings.web_host, port=settings.web_port, debug=False)


if __name__ == "__main__":
    main()
