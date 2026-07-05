import yfinance as yf

from stockapp_notion.config import settings
from stockapp_notion.logging_config import get_logger
from stockapp_notion.notion_api import call_with_retry, get_client
from stockapp_notion.notion_helpers import prop_rich_text, prop_select_name, prop_title
from stockapp_notion.stocks import list_stocks, yfinance_ticker

logger = get_logger(__name__)


def fetch_current_price(code: str, market: str) -> float | None:
    ticker = yfinance_ticker(code, market)
    try:
        info = yf.Ticker(ticker).fast_info
        price = info.last_price
        if price is None:
            raise ValueError("last_price가 비어 있습니다")
        return float(price)
    except Exception:
        logger.exception("시세 조회 실패: %s (%s)", code, ticker)
        return None


def update_all_prices(client=None) -> dict[str, int]:
    """종목 마스터 DB의 모든 종목에 대해 현재가를 갱신한다.
    성공/실패 개수를 반환하여 배치 실행 결과를 로그로 남길 수 있게 한다."""
    client = client or get_client()
    stocks = list_stocks(client=client)

    success, failed = 0, 0
    for page in stocks:
        name = prop_title(page, "종목명") or page["id"]
        code = prop_rich_text(page, "종목코드")
        market = prop_select_name(page, "시장구분")

        price = fetch_current_price(code, market)
        if price is None:
            failed += 1
            continue

        call_with_retry(
            client.pages.update,
            page_id=page["id"],
            properties={"현재가": {"number": price}},
        )
        logger.info("현재가 갱신: %s(%s) -> %s", name, code, price)
        success += 1

    logger.info("현재가 갱신 완료: 성공 %s건, 실패 %s건", success, failed)
    return {"success": success, "failed": failed}
