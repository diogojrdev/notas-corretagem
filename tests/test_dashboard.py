import pandas as pd
import pytest

from notas_corretagem.dashboard import build_by_asset, filter_trades

TRADE_COLUMNS = [
    "trading_date",
    "asset_name",
    "ticker",
    "market_type",
    "side",
    "quantity",
    "price",
    "value",
    "market",
]

COST_COLUMNS = ["trading_date", "market", "fees", "irrf"]


def make_trades(rows):
    return pd.DataFrame(rows, columns=TRADE_COLUMNS)


def test_build_by_asset_with_empty_trades():
    trades = make_trades([])
    costs = pd.DataFrame(columns=COST_COLUMNS)

    result = build_by_asset(trades, costs)

    assert result.empty


def test_build_by_asset_allocates_costs_by_volume():
    day = pd.Timestamp("2026-08-01")
    trades = make_trades(
        [
            [day, "ASSET A", "AAA", "VISTA", "C", 60, 10.0, 600.0, "VISTA"],
            [day, "ASSET B", "BBB", "VISTA", "V", 40, 10.0, -400.0, "VISTA"],
        ]
    )
    costs = pd.DataFrame([[day, "VISTA", 100.0, 0.0]], columns=COST_COLUMNS)

    result = build_by_asset(trades, costs)

    assert result.loc["ASSET A", "gross_result"] == pytest.approx(600.0)
    assert result.loc["ASSET B", "gross_result"] == pytest.approx(-400.0)
    assert result.loc["ASSET A", "allocated_costs"] == pytest.approx(60.0)
    assert result.loc["ASSET B", "allocated_costs"] == pytest.approx(40.0)
    assert result.loc["ASSET A", "net_result"] == pytest.approx(540.0)
    assert result.loc["ASSET B", "net_result"] == pytest.approx(-440.0)
    assert list(result.index) == ["ASSET A", "ASSET B"]


def make_filter_trades():
    day1 = pd.Timestamp("2026-08-01")
    day2 = pd.Timestamp("2026-08-02")
    return make_trades(
        [
            [day1, "PETR4", "PETR4", "VISTA", "C", 100, 30.0, 3000.0, "BOVESPA"],
            [day1, "VALE3", "VALE3", "VISTA", "V", 50, 60.0, -3000.0, "BOVESPA"],
            [day2, "DI1F37", "DI1F37", "FUT", "C", 1, 10.0, 500.0, "BMF"],
        ]
    )


def test_filter_trades_market_only_returns_all_market_assets():
    trades = make_filter_trades()

    result = filter_trades(trades, (), ["BOVESPA"], [])

    assert list(result["asset_name"]) == ["PETR4", "VALE3"]


def test_filter_trades_no_filters_returns_everything():
    trades = make_filter_trades()

    result = filter_trades(trades, (), [], [])

    assert len(result) == 3


def test_filter_trades_market_and_asset_intersect():
    trades = make_filter_trades()

    result = filter_trades(trades, (), ["BMF"], ["PETR4"])

    assert result.empty


def test_filter_trades_date_range():
    trades = make_filter_trades()

    result = filter_trades(trades, (pd.Timestamp("2026-08-02").date(), pd.Timestamp("2026-08-02").date()), [], [])

    assert list(result["asset_name"]) == ["DI1F37"]
