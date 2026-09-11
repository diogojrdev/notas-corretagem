import pandas as pd
import pytest

from notas_corretagem.dashboard import (
    build_by_asset,
    build_closed_operations,
    build_daily,
    filter_trades,
)

TRADE_COLUMNS = [
    "trade_id",
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
            [1, day, "ASSET A", "AAA", "VISTA", "C", 60, 10.0, 600.0, "VISTA"],
            [2, day, "ASSET B", "BBB", "VISTA", "V", 40, 10.0, -400.0, "VISTA"],
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


def test_build_by_asset_does_not_allocate_irrf():
    day = pd.Timestamp("2026-08-01")
    trades = make_trades(
        [
            [1, day, "ASSET A", "AAA", "VISTA", "C", 60, 10.0, 600.0, "BOVESPA"],
            [2, day, "ASSET B", "BBB", "VISTA", "V", 40, 10.0, -400.0, "BOVESPA"],
        ]
    )
    costs = pd.DataFrame([[day, "BOVESPA", 80.0, 20.0]], columns=COST_COLUMNS)

    result = build_by_asset(trades, costs)

    assert result.loc["ASSET A", "allocated_costs"] == pytest.approx(48.0)
    assert result.loc["ASSET B", "allocated_costs"] == pytest.approx(32.0)
    assert result.loc["ASSET A", "net_result"] == pytest.approx(552.0)
    assert result.loc["ASSET B", "net_result"] == pytest.approx(-432.0)


def test_build_daily_net_result_excludes_irrf():
    day = pd.Timestamp("2026-08-01")
    trades = make_trades(
        [
            [1, day, "ASSET A", "AAA", "VISTA", "C", 100, 10.0, -1000.0, "BOVESPA"],
            [2, day, "ASSET A", "AAA", "VISTA", "V", 100, 10.5, 1050.0, "BOVESPA"],
        ]
    )
    costs = pd.DataFrame([[day, "BOVESPA", 10.0, 5.0]], columns=COST_COLUMNS)

    daily = build_daily(trades, costs)

    assert daily.loc[day, "gross_result"] == pytest.approx(50.0)
    assert daily.loc[day, "fees"] == pytest.approx(10.0)
    assert daily.loc[day, "irrf"] == pytest.approx(5.0)
    assert daily.loc[day, "net_result"] == pytest.approx(40.0)


def test_build_closed_operations_with_empty_trades():
    result = build_closed_operations(make_trades([]), pd.DataFrame(columns=COST_COLUMNS))

    assert result.empty


def test_closed_operations_single_pair_with_embedded_costs():
    day = pd.Timestamp("2026-08-26")
    trades = make_trades(
        [
            [1, day, "ASSET A", "AAA", "VISTA", "C", 200, 5.15, -1030.0, "BOVESPA"],
            [2, day, "ASSET A", "AAA", "FRACIONARIO", "V", 30, 5.14, 154.2, "BOVESPA"],
            [3, day, "ASSET A", "AAA", "FRACIONARIO", "V", 170, 5.18, 880.6, "BOVESPA"],
        ]
    )
    costs = pd.DataFrame([[day, "BOVESPA", 0.75, 0.18]], columns=COST_COLUMNS)

    result = build_closed_operations(trades, costs)

    assert len(result) == 1
    row = result.iloc[0]
    assert row["quantity"] == 200
    assert row["direction"] == "C→V"
    assert row["avg_price"] == pytest.approx(5.1519, abs=1e-4)
    assert row["final_price"] == pytest.approx(5.1721, abs=1e-4)
    assert row["result"] == pytest.approx(4.0499, abs=1e-3)
    assert row["profitability"] == pytest.approx(0.3931, abs=1e-3)


def test_closed_operations_merges_round_turns_split_by_partial_sell():
    day = pd.Timestamp("2026-08-31")
    trades = make_trades(
        [
            [1, day, "ASSET G", "GGG", "FRACIONARIO", "C", 250, 23.68, -5920.0, "BOVESPA"],
            [2, day, "ASSET G", "GGG", "FRACIONARIO", "C", 50, 23.69, -1184.5, "BOVESPA"],
            [3, day, "ASSET G", "GGG", "FRACIONARIO", "C", 8, 23.70, -189.6, "BOVESPA"],
            [4, day, "ASSET G", "GGG", "FRACIONARIO", "V", 8, 23.67, 189.36, "BOVESPA"],
            [5, day, "ASSET G", "GGG", "VISTA", "V", 200, 23.80, 4760.0, "BOVESPA"],
            [6, day, "ASSET G", "GGG", "VISTA", "V", 100, 23.81, 2381.0, "BOVESPA"],
        ]
    )
    costs = pd.DataFrame([[day, "BOVESPA", 3.11, 0.33]], columns=COST_COLUMNS)

    result = build_closed_operations(trades, costs)

    assert len(result) == 2
    assert list(result["quantity"]) == [250, 58]
    assert result.iloc[0]["direction"] == "C→V"
    assert result.iloc[1]["direction"] == "V→C"
    assert result.iloc[0]["result"] == pytest.approx(26.856, abs=1e-3)
    assert result.iloc[1]["result"] == pytest.approx(6.294, abs=1e-3)
    assert result["result"].sum() == pytest.approx(33.15, abs=1e-6)


def test_closed_operations_bmf_prices_are_signed_adjustments():
    day = pd.Timestamp("2026-08-27")
    trades = make_trades(
        [
            [1, day, "ASSET S", "SSS", "FUT", "V", 5, 109.12, -22.70, "BMF"],
            [2, day, "ASSET S", "SSS", "FUT", "C", 1, 108.60, 17.96, "BMF"],
            [3, day, "ASSET S", "SSS", "FUT", "C", 4, 108.99, 31.56, "BMF"],
        ]
    )
    costs = pd.DataFrame([[day, "BMF", 3.00, 0.23]], columns=COST_COLUMNS)

    result = build_closed_operations(trades, costs)

    assert len(result) == 1
    row = result.iloc[0]
    assert row["quantity"] == 5
    assert row["direction"] == "V→C"
    assert row["avg_price"] == pytest.approx(-4.7286, abs=1e-4)
    assert row["final_price"] == pytest.approx(9.4926, abs=1e-4)
    assert row["result"] == pytest.approx(23.82, abs=1e-6)
    assert row["profitability"] == pytest.approx(100.75, abs=0.01)


def test_closed_operations_reports_open_position():
    day = pd.Timestamp("2026-08-01")
    trades = make_trades(
        [
            [1, day, "ASSET A", "AAA", "VISTA", "C", 100, 10.0, -1000.0, "BOVESPA"],
            [2, day, "ASSET A", "AAA", "VISTA", "V", 60, 10.5, 630.0, "BOVESPA"],
        ]
    )
    costs = pd.DataFrame([[day, "BOVESPA", 10.0, 0.0]], columns=COST_COLUMNS)

    result = build_closed_operations(trades, costs)

    closed = result[result["direction"].isin(["C→V", "V→C"])]
    open_position = result[result["direction"] == "C"]
    assert len(closed) == 1
    assert closed.iloc[0]["quantity"] == 60
    assert closed.iloc[0]["result"] == pytest.approx(22.454, abs=1e-2)
    assert len(open_position) == 1
    assert open_position.iloc[0]["quantity"] == 40
    assert pd.isna(open_position.iloc[0]["result"])


def make_filter_trades():
    day1 = pd.Timestamp("2026-08-01")
    day2 = pd.Timestamp("2026-08-02")
    return make_trades(
        [
            [1, day1, "PETR4", "PETR4", "VISTA", "C", 100, 30.0, 3000.0, "BOVESPA"],
            [2, day1, "VALE3", "VALE3", "VISTA", "V", 50, 60.0, -3000.0, "BOVESPA"],
            [3, day2, "DI1F37", "DI1F37", "FUT", "C", 1, 10.0, 500.0, "BMF"],
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
