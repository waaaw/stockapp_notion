from stockapp_notion.portfolio import aggregate_totals


def _h(currency, valuation, profit, realized_pnl=0.0, total_return=None):
    return {
        "currency": currency,
        "valuation": valuation,
        "profit": profit,
        "realized_pnl": realized_pnl,
        "total_return": total_return if total_return is not None else profit + realized_pnl,
    }


# KRW은 1.0, USD/CNY는 고정 스텁 환율 (네트워크 없이 테스트)
def _fx(currency):
    return {"KRW": 1.0, "USD": 1000.0, "CNY": 200.0}.get(currency)


def test_single_currency_no_conversion():
    summary = [_h("KRW", 3_000_000, 500_000)]
    t = aggregate_totals(summary, _fx)
    assert t["multi_currency"] is False
    assert t["krw"]["valuation"] == 3_000_000
    assert t["krw"]["profit"] == 500_000
    assert t["fx_incomplete"] is False


def test_multi_currency_krw_conversion():
    summary = [_h("KRW", 3_000_000, 500_000), _h("USD", 1_000, 200)]
    t = aggregate_totals(summary, _fx)
    assert t["multi_currency"] is True
    # KRW 환산: 3,000,000 + 1,000 * 1000 = 4,000,000
    assert t["krw"]["valuation"] == 4_000_000
    # 손익: 500,000 + 200 * 1000 = 700,000
    assert t["krw"]["profit"] == 700_000
    assert t["by_currency"]["USD"]["valuation"] == 1_000
    assert t["fx_rates"]["USD"] == 1000.0


def test_return_pct_computed_from_krw_totals():
    summary = [_h("USD", 1_100, 100)]  # 원가 1000, 이익 100 -> 10%
    t = aggregate_totals(summary, _fx)
    assert round(t["krw"]["return_pct"], 2) == 10.0


def test_fx_incomplete_when_rate_missing():
    summary = [_h("KRW", 1_000_000, 0), _h("HKD", 500, 50)]
    t = aggregate_totals(summary, _fx)  # HKD는 스텁에 없어 None
    assert t["fx_incomplete"] is True
    # HKD는 환산에서 제외 -> KRW 총계는 KRW 종목만
    assert t["krw"]["valuation"] == 1_000_000
    # 통화별 소계에는 HKD가 원화폐 기준으로 남아 있음
    assert t["by_currency"]["HKD"]["valuation"] == 500
