import argparse
import sys

from stockapp_notion.dividends import add_dividend
from stockapp_notion.logging_config import get_logger
from stockapp_notion.notion_api import get_client
from stockapp_notion.portfolio import sync_all_portfolios
from stockapp_notion.prices import update_all_prices
from stockapp_notion.stocks import add_stock, find_stock_by_code
from stockapp_notion.transactions import add_transaction

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


def cmd_daily_update(_args: argparse.Namespace) -> None:
    """cron/스케줄러에서 호출하는 일 배치: 현재가 갱신 후 포트폴리오 재계산."""
    update_all_prices()
    sync_all_portfolios()


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
    p.add_argument("--type", required=True, choices=["매수", "매도"])
    p.add_argument("--qty", required=True, type=float)
    p.add_argument("--price", required=True, type=float)
    p.add_argument("--fee", type=float, default=0)
    p.add_argument("--date", required=True, help="YYYY-MM-DD")
    p.set_defaults(func=cmd_add_transaction)

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
