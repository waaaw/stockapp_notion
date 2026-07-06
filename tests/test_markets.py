from stockapp_notion.markets import default_currency, ticker_suffix
from stockapp_notion.stocks import yfinance_ticker


def test_domestic_ticker_suffix():
    assert yfinance_ticker("005930", "코스피") == "005930.KS"
    assert yfinance_ticker("035720", "코스닥") == "035720.KQ"


def test_us_ticker_no_suffix():
    assert yfinance_ticker("AAPL", "나스닥") == "AAPL"
    assert yfinance_ticker("KO", "NYSE") == "KO"


def test_china_and_hk_ticker_suffix():
    assert yfinance_ticker("600519", "상해") == "600519.SS"
    assert yfinance_ticker("000001", "심천") == "000001.SZ"
    assert yfinance_ticker("0700", "홍콩") == "0700.HK"


def test_unknown_market_has_no_suffix():
    assert ticker_suffix("존재하지않는시장") == ""
    assert yfinance_ticker("XYZ", "기타") == "XYZ"


def test_default_currency_inference():
    assert default_currency("코스피") == "KRW"
    assert default_currency("나스닥") == "USD"
    assert default_currency("상해") == "CNY"
    assert default_currency("홍콩") == "HKD"
