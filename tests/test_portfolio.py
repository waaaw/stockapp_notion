from stockapp_notion.portfolio import compute_holding
from stockapp_notion.transactions import compute_total_amount


def _tx(buy_sell: str, qty: float, price: float) -> dict:
    return {
        "properties": {
            "수량": {"number": qty},
            "단가": {"number": price},
            "매매구분": {"select": {"name": buy_sell}},
        }
    }


def test_compute_holding_single_buy():
    holding = compute_holding([_tx("매수", 10, 1000)])
    assert holding.qty == 10
    assert holding.avg_price == 1000


def test_compute_holding_weighted_average():
    holding = compute_holding([_tx("매수", 10, 1000), _tx("매수", 10, 2000)])
    assert holding.qty == 20
    assert holding.avg_price == 1500


def test_compute_holding_partial_sell_keeps_avg_price():
    holding = compute_holding([_tx("매수", 10, 1000), _tx("매도", 4, 1200)])
    assert holding.qty == 6
    assert holding.avg_price == 1000


def test_compute_holding_full_sell_resets():
    holding = compute_holding([_tx("매수", 10, 1000), _tx("매도", 10, 1200)])
    assert holding.qty == 0
    assert holding.avg_price == 0


def test_compute_total_amount_buy_adds_fee():
    assert compute_total_amount("매수", 10, 1000, 50) == 10_050


def test_compute_total_amount_sell_subtracts_fee():
    assert compute_total_amount("매도", 10, 1000, 50) == 9_950
