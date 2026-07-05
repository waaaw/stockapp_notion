import argparse
import sys

from stockapp_notion.dividends import add_dividend
from stockapp_notion.logging_config import get_logger
from stockapp_notion.notion_api import get_client
from stockapp_notion.portfolio import sync_all_portfolios, sync_portfolio_for_stock
from stockapp_notion.prices import update_all_prices
from stockapp_notion.stocks import add_stock, find_stock_by_code
from stockapp_notion.transactions import (
    TRADE_TYPES,
    add_transaction,
    delete_transaction,
    list_transactions_for_stock,
    update_transaction,
)

logger = get_logger(__name__)


def _resolve_stock_id(client, code: str) -> str:
    stock = find_stock_by_code(code, client=client)
    if not stock:
        raise SystemExit(f"종목코드 {code}를 종목 마스터 DB에서 찾을 수 없습니다. 먼저 add-stock으로 등록하세요.")
    return stock["id"]


def cmd_add_stock(args: argparse.Namespace) -> None:
    client = get_client()
    add_stock(
        name=args.name,
        code=args.code,
        market=args.market,
        sector=args.sector,
        currency=args.currency,
        client=client,
    )


def cmd_add_transaction(args: argparse.Namespace) -> None:
    client = get_client()
    stock_id = _resolve_stock_id(client, args.code)
    add_transaction(
        stock_page_id=stock_id,
        trade_date=args.date,
        buy_sell=args.type,
        qty=args.qty,
        price=args.price,
        fee=args.fee,
        client=client,
    )
    sync_all_portfolios(client=client)


def cmd_list_transactions(args: argparse.Namespace) -> None:
    client = get_client()
    stock_id = _resolve_stock_id(client, args.code)
    transactions = list_transactions_for_stock(stock_id, client=client)
    if not transactions:
        print("매매내역이 없습니다.")
        return
    for tx in transactions:
        props = tx["properties"]
        print(
            f"{tx['id']}  {props['거래일자']['date']['start']}  "
            f"{props['매매구분']['select']['name']}  "
            f"{props['수량']['number']}주 @ {props['단가']['number']}  "
            f"수수료 {props['수수료']['number']}"
        )


def cmd_edit_transaction(args: argparse.Namespace) -> None:
    client = get_client()
    tx = update_transaction(
        args.transaction_id,
        trade_date=args.date,
        buy_sell=args.type,
        qty=args.qty,
        price=args.price,
        fee=args.fee,
        client=client,
    )
    stock_id = tx["properties"]["종목"]["relation"][0]["id"]
    stock = client.pages.retrieve(page_id=stock_id)
    sync_portfolio_for_stock(stock, client=client)


def cmd_delete_transaction(args: argparse.Namespace) -> None:
    client = get_client()
    tx = client.pages.retrieve(page_id=args.transaction_id)
    stock_id = tx["properties"]["종목"]["relation"][0]["id"]
    delete_transaction(args.transaction_id, client=client)
    stock = client.pages.retrieve(page_id=stock_id)
    sync_portfolio_for_stock(stock, client=client)


def cmd_add_dividend(args: argparse.Namespace) -> None:
    client = get_client()
    stock_id = _resolve_stock_id(client, args.code)
    add_dividend(
        stock_page_id=stock_id,
        pay_date=args.date,
        pretax_amount=args.pretax,
        posttax_amount=args.posttax,
        client=client,
    )


def cmd_update_prices(_args: argparse.Namespace) -> None:
    update_all_prices()


def cmd_sync_portfolio(_args: argparse.Namespace) -> None:
    sync_all_portfolios()


def cmd_kis_check_balance(_args: argparse.Namespace) -> None:
    """KIS 계좌 잔고와 Notion 기록을 교차검증한다(읽기 전용, 아무것도 덮어쓰지 않음)."""
    from stockapp_notion.kis_api import check_balance_against_notion

    discrepancies = check_balance_against_notion()
    if discrepancies:
        print(f"불일치 {len(discrepancies)}건:")
        for d in discrepancies:
            print(f"  - {d}")
    else:
        print("KIS 계좌와 Notion 기록이 일치합니다.")


def cmd_daily_update(_args: argparse.Namespace) -> None:
    """cron/스케줄러에서 호출하는 일 배치: 현재가 갱신 후 포트폴리오 재계산.
    KIS가 설정되어 있으면 잔고 교차검증도 수행한다(로그만 남김)."""
    from stockapp_notion.config import settings

    update_all_prices()
    sync_all_portfolios()
    if settings.kis_enabled:
        from stockapp_notion.kis_api import check_balance_against_notion

        try:
            check_balance_against_notion()
        except Exception:
            logger.exception("KIS 잔고 교차검증 실패 (일일 배치는 계속 진행됨)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="stockapp-notion", description="Notion 기반 주식 포트폴리오 관리 CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("add-stock", help="종목 마스터 DB에 신규 종목 등록")
    p.add_argument("--name", required=True)
    p.add_argument("--code", required=True)
    p.add_argument("--market", required=True, choices=["코스피", "코스닥", "나스닥", "NYSE", "기타"])
    p.add_argument("--sector", required=True)
    p.add_argument("--currency", required=True, choices=["KRW", "USD"])
    p.set_defaults(func=cmd_add_stock)

    p = sub.add_parser("add-transaction", help="매매내역 등록 + 포트폴리오 재계산")
    p.add_argument("--code", required=True, help="종목코드")
    p.add_argument("--type", required=True, choices=list(TRADE_TYPES))
    p.add_argument("--qty", required=True, type=float)
    p.add_argument("--price", required=True, type=float)
    p.add_argument("--fee", type=float, default=0)
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.set_defaults(func=cmd_add_transaction)

    p = sub.add_parser("list-transactions", help="특정 종목의 매매내역 조회 (페이지ID 확인용)")
    p.add_argument("--code", required=True, help="종목코드")
    p.set_defaults(func=cmd_list_transactions)

    p = sub.add_parser("edit-transaction", help="매매내역 수정 (변경할 항목만 지정)")
    p.add_argument("--transaction-id", required=True, help="list-transactions로 확인한 페이지ID")
    p.add_argument("--type", choices=list(TRADE_TYPES))
    p.add_argument("--qty", type=float)
    p.add_argument("--price", type=float)
    p.add_argument("--fee", type=float)
    p.add_argument("--date", help="YYYY-MM-DD")
    p.set_defaults(func=cmd_edit_transaction)

    p = sub.add_parser("delete-transaction", help="매매내역 삭제 (휴지통 이동, 복구 가능)")
    p.add_argument("--transaction-id", required=True, help="list-transactions로 확인한 페이지ID")
    p.set_defaults(func=cmd_delete_transaction)

    p = sub.add_parser("add-dividend", help="배당금 내역 등록")
    p.add_argument("--code", required=True)
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.add_argument("--pretax", required=True, type=float)
    p.add_argument("--posttax", required=True, type=float)
    p.set_defaults(func=cmd_add_dividend)

    p = sub.add_parser("update-prices", help="전 종목 현재가 갱신")
    p.set_defaults(func=cmd_update_prices)

    p = sub.add_parser("sync-portfolio", help="포트폴리오 요약 DB 재계산")
    p.set_defaults(func=cmd_sync_portfolio)

    p = sub.add_parser("daily-update", help="현재가 갱신 + 포트폴리오 재계산 (cron용)")
    p.set_defaults(func=cmd_daily_update)

    p = sub.add_parser("kis-check-balance", help="KIS 계좌 잔고와 Notion 기록 교차검증 (읽기 전용)")
    p.set_defaults(func=cmd_kis_check_balance)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except Exception:
        logger.exception("명령 실행 중 오류 발생: %s", args.command)
        sys.exit(1)


if __name__ == "__main__":
    main()
