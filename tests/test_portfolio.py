from stockapp_notion.portfolio import compute_holding, compute_realized_gains
from stockapp_notion.transactions import compute_total_amount


def _tx(buy_sell: str, qty: float, price: float, fee: float = 0, trade_date: str = "2026-01-01") -> dict:
    return {
        "properties": {
            "수량": {"number": qty},
            "단가": {"number": price},
            "수수료": {"number": fee},
            "거래일자": {"date": {"start": trade_date}},
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


def test_compute_realized_gains_single_sell():
    gains = compute_realized_gains([_tx("매수", 10, 1000), _tx("매도", 4, 1200, fee=10)])
    assert len(gains) == 1
    gain = gains[0]
    assert gain.qty == 4
    assert gain.sell_price == 1200
    assert gain.avg_cost_at_sale == 1000
    # (1200 - 1000) * 4 - 10 = 790
    assert gain.realized_pnl == 790


def test_compute_realized_gains_no_sells_is_empty():
    assert compute_realized_gains([_tx("매수", 10, 1000)]) == []


def test_compute_realized_gains_multiple_sells_use_avg_at_each_point():
    gains = compute_realized_gains(
        [
            _tx("매수", 10, 1000),
            _tx("매도", 5, 1500),  # realized: (1500-1000)*5 = 2500
            _tx("매수", 5, 2000),  # avg becomes (5*1000 + 5*2000)/10 = 1500
            _tx("매도", 5, 1800),  # realized: (1800-1500)*5 = 1500
        ]
    )
    assert len(gains) == 2
    assert gains[0].realized_pnl == 2500
    assert gains[1].realized_pnl == 1500
