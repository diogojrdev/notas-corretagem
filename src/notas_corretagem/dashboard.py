from collections import deque
from io import BytesIO

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from notas_corretagem.config import get_settings
from notas_corretagem.importer import import_bytes
from notas_corretagem.models import BrokerageNote, BrokerageTrade, NoteCosts
from notas_corretagem.parser import parse_pdf

st.set_page_config(page_title="Notas de Corretagem", page_icon="📊", layout="wide")

COST_COLUMNS = [
    "settlement_fee",
    "registration_fee",
    "emoluments",
    "brokerage_fee",
    "iss",
    "other_fees",
]


@st.cache_resource
def get_engine():
    return create_engine(get_settings().sqlalchemy_url)


@st.cache_data(ttl=30)
def load_trades() -> pd.DataFrame:
    query = select(
        BrokerageTrade.id.label("trade_id"),
        BrokerageTrade.trading_date,
        BrokerageTrade.asset_name,
        BrokerageTrade.ticker,
        BrokerageTrade.market_type,
        BrokerageTrade.side,
        BrokerageTrade.quantity,
        BrokerageTrade.price,
        BrokerageTrade.value,
        BrokerageNote.market,
    ).join(BrokerageNote, BrokerageTrade.note_id == BrokerageNote.id)
    df = pd.read_sql(query, get_engine())
    df["trading_date"] = pd.to_datetime(df["trading_date"])
    for col in ("price", "value"):
        df[col] = df[col].astype(float)
    return df


@st.cache_data(ttl=30)
def load_costs() -> pd.DataFrame:
    query = select(
        BrokerageNote.trading_date,
        BrokerageNote.market,
        NoteCosts.settlement_fee,
        NoteCosts.registration_fee,
        NoteCosts.emoluments,
        NoteCosts.brokerage_fee,
        NoteCosts.iss,
        NoteCosts.other_fees,
        NoteCosts.irrf,
    ).join(BrokerageNote, NoteCosts.note_id == BrokerageNote.id)
    df = pd.read_sql(query, get_engine())
    df["trading_date"] = pd.to_datetime(df["trading_date"])
    for col in df.columns:
        if col not in ("trading_date", "market"):
            df[col] = df[col].astype(float)
    df["fees"] = df[COST_COLUMNS].abs().sum(axis=1)
    df["irrf"] = df["irrf"].abs()
    return df[["trading_date", "market", "fees", "irrf"]]


def fmt_brl(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_price(value: float) -> str:
    return f"{value:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_pct(value: float) -> str:
    return f"{value:,.2f}%".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_qty(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return fmt_price(value)


def build_daily(trades: pd.DataFrame, costs: pd.DataFrame) -> pd.DataFrame:
    abs_value = trades["value"].abs()
    gross = trades.groupby("trading_date")["value"].sum().to_frame("gross_result")
    volume = abs_value.groupby(trades["trading_date"]).sum().to_frame("volume")
    operations = trades.groupby("trading_date").size().to_frame("operations")

    daily_costs = costs.groupby("trading_date")[["fees", "irrf"]].sum()

    daily = gross.join(volume).join(operations).join(daily_costs, how="left").fillna(0.0)
    daily["net_result"] = daily["gross_result"] - daily["fees"]
    daily["cumulative"] = daily["net_result"].cumsum()
    return daily.sort_index()


def build_by_asset(trades: pd.DataFrame, costs: pd.DataFrame) -> pd.DataFrame:
    abs_value = trades["value"].abs()
    gross = trades.groupby("asset_name")["value"].sum().to_frame("gross_result")
    volume = abs_value.groupby(trades["asset_name"]).sum().to_frame("volume")
    operations = trades.groupby("asset_name").size().to_frame("operations")
    market = trades.groupby("asset_name")["market"].first()

    daily_asset_volume = abs_value.groupby([trades["trading_date"], trades["asset_name"]]).sum()
    daily_volume = abs_value.groupby(trades["trading_date"]).sum()
    daily_fees = costs.groupby("trading_date")["fees"].sum()

    allocated = []
    for (day, asset), vol in daily_asset_volume.items():
        day_fees = daily_fees.loc[day] if day in daily_fees.index else 0.0
        allocated.append({"asset_name": asset, "allocated_costs": day_fees * vol / daily_volume.loc[day]})
    allocation = (
        pd.DataFrame(allocated, columns=["asset_name", "allocated_costs"])
        .groupby("asset_name")["allocated_costs"]
        .sum()
    )

    by_asset = (
        gross.join(volume)
        .join(operations)
        .join(market)
        .join(allocation)
        .fillna(0.0)
    )
    by_asset["net_result"] = by_asset["gross_result"] - by_asset["allocated_costs"]
    return by_asset.sort_values("net_result", ascending=False)


def _pair_round_turns(buys: list[dict], sells: list[dict]) -> tuple[list[dict], dict]:
    """Casa compras contra vendas em FIFO; lotes de compra consecutivos que
    abrem e fecham a mesma venda parcial são fundidos em um único pareamento."""
    sell_queue = deque(
        {"id": i, "quantity": s["quantity"], "total": s["quantity"], "value": s["value"]}
        for i, s in enumerate(sells)
    )
    pairs: list[dict] = []
    open_sell_id = None
    leftover = {"quantity": 0, "value": 0.0, "sell_quantity": 0, "sell_value": 0.0}

    for buy_id, buy in enumerate(buys):
        total = buy["quantity"]
        remaining = total
        pair = {
            "quantity": 0,
            "buy_value": 0.0,
            "buy_abs": 0.0,
            "buy_ids": set(),
            "sell_value": 0.0,
            "sell_abs": 0.0,
            "sell_ids": set(),
            "opened_by": open_sell_id,
            "closed_by": None,
        }
        while remaining > 0 and sell_queue:
            sell = sell_queue[0]
            matched = min(remaining, sell["quantity"])
            pair["quantity"] += matched
            pair["buy_value"] += buy["value"] * matched / total
            pair["buy_abs"] += abs(buy["value"]) * matched / total
            pair["sell_value"] += sell["value"] * matched / sell["total"]
            pair["sell_abs"] += abs(sell["value"]) * matched / sell["total"]
            pair["buy_ids"].add(buy_id)
            pair["sell_ids"].add(sell["id"])
            remaining -= matched
            sell["quantity"] -= matched
            if sell["quantity"] == 0:
                pair["closed_by"] = sell["id"]
                sell_queue.popleft()

        if pair["quantity"] > 0:
            pairs.append(pair)
        if remaining > 0:
            leftover["quantity"] += remaining
            leftover["value"] += buy["value"] * remaining / total
        open_sell_id = sell_queue[0]["id"] if sell_queue else None

    while sell_queue:
        sell = sell_queue.popleft()
        leftover["sell_quantity"] += sell["quantity"]
        leftover["sell_value"] += sell["value"]

    merged: list[dict] = []
    for pair in pairs:
        if pair["opened_by"] is not None and pair["opened_by"] == pair["closed_by"] and merged:
            previous = merged[-1]
            previous["quantity"] += pair["quantity"]
            previous["buy_value"] += pair["buy_value"]
            previous["buy_abs"] += pair["buy_abs"]
            previous["buy_ids"] |= pair["buy_ids"]
            previous["sell_value"] += pair["sell_value"]
            previous["sell_abs"] += pair["sell_abs"]
            previous["sell_ids"] |= pair["sell_ids"]
        else:
            merged.append(pair)
    return merged, leftover


OPERATION_COLUMNS = [
    "trading_date",
    "market",
    "asset_name",
    "quantity",
    "direction",
    "avg_price",
    "final_price",
    "profitability",
    "result",
]


def build_closed_operations(trades: pd.DataFrame, costs: pd.DataFrame) -> pd.DataFrame:
    """Pareia compras e vendas do mesmo ativo no mesmo pregão com os custos do
    dia embutidos em cada perna, proporcionalmente ao valor financeiro."""
    if trades.empty:
        return pd.DataFrame(columns=OPERATION_COLUMNS)

    day_fees = costs.groupby("trading_date")["fees"].sum()
    day_volume = trades["value"].abs().groupby(trades["trading_date"]).sum()

    rows = []
    for (day, asset), group in trades.sort_values("trade_id").groupby(
        ["trading_date", "asset_name"]
    ):
        market = group["market"].iloc[0]
        buys = group[group["side"] == "C"].to_dict("records")
        sells = group[group["side"] == "V"].to_dict("records")
        pairs, leftover = _pair_round_turns(buys, sells)

        fees = float(day_fees.loc[day]) if day in day_fees.index else 0.0
        volume = float(day_volume.loc[day])

        for pair in pairs:
            buy_cost = fees * pair["buy_abs"] / volume
            sell_cost = fees * pair["sell_abs"] / volume
            result = pair["buy_value"] + pair["sell_value"] - buy_cost - sell_cost
            if market == "BOVESPA":
                buy_total = pair["buy_abs"] + buy_cost
                sell_total = pair["sell_abs"] - sell_cost
            else:
                buy_total = pair["buy_value"] - buy_cost
                sell_total = pair["sell_value"] - sell_cost
            buy_avg = buy_total / pair["quantity"]
            sell_avg = sell_total / pair["quantity"]
            denominator = min(abs(buy_total), abs(sell_total))
            profitability = 100 * result / denominator if denominator else float("nan")
            buys_first = len(pair["buy_ids"]) <= len(pair["sell_ids"])
            rows.append(
                {
                    "trading_date": day,
                    "market": market,
                    "asset_name": asset,
                    "quantity": pair["quantity"],
                    "direction": "C→V" if buys_first else "V→C",
                    "avg_price": buy_avg if buys_first else sell_avg,
                    "final_price": sell_avg if buys_first else buy_avg,
                    "profitability": profitability,
                    "result": result,
                }
            )

        if leftover["quantity"] > 0:
            rows.append(
                {
                    "trading_date": day,
                    "market": market,
                    "asset_name": asset,
                    "quantity": leftover["quantity"],
                    "direction": "C",
                    "avg_price": abs(leftover["value"]) / leftover["quantity"],
                    "final_price": float("nan"),
                    "profitability": float("nan"),
                    "result": float("nan"),
                }
            )
        if leftover["sell_quantity"] > 0:
            rows.append(
                {
                    "trading_date": day,
                    "market": market,
                    "asset_name": asset,
                    "quantity": leftover["sell_quantity"],
                    "direction": "V",
                    "avg_price": abs(leftover["sell_value"]) / leftover["sell_quantity"],
                    "final_price": float("nan"),
                    "profitability": float("nan"),
                    "result": float("nan"),
                }
            )

    return pd.DataFrame(rows, columns=OPERATION_COLUMNS).sort_values(
        ["trading_date", "asset_name"]
    )


def filter_trades(
    trades: pd.DataFrame,
    date_range: tuple,
    markets: list[str],
    assets: list[str],
) -> pd.DataFrame:
    """Filtra trades por período, mercado e ativo; lista vazia significa sem filtro."""
    mask = pd.Series(True, index=trades.index)
    if len(date_range) == 2:
        mask &= trades["trading_date"].between(pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1]))
    if markets:
        mask &= trades["market"].isin(markets)
    if assets:
        mask &= trades["asset_name"].isin(assets)
    return trades[mask]


def render_overview():
    trades = load_trades()
    if trades.empty:
        st.info("Nenhuma negociação no banco. Use a aba **Importar** para enviar os PDFs das notas.")
        return

    costs = load_costs()

    with st.sidebar:
        st.header("Filtros")
        date_range = st.date_input(
            "Período",
            value=(trades["trading_date"].min().date(), trades["trading_date"].max().date()),
        )
        markets = st.multiselect(
            "Mercado", sorted(trades["market"].unique()), default=sorted(trades["market"].unique())
        )
        market_assets = trades["asset_name"]
        if markets:
            market_assets = trades.loc[trades["market"].isin(markets), "asset_name"]
        assets = st.multiselect(
            "Ativo",
            sorted(market_assets.unique()),
            help="Vazio = todos os ativos do(s) mercado(s) selecionado(s)",
        )

    filtered_trades = filter_trades(trades, date_range, markets, assets)
    if filtered_trades.empty:
        st.info("Nenhuma negociação encontrada com os filtros selecionados.")
        return

    cost_mask = pd.Series(True, index=costs.index)
    if len(date_range) == 2:
        cost_mask &= costs["trading_date"].between(pd.Timestamp(date_range[0]), pd.Timestamp(date_range[1]))
    if markets:
        cost_mask &= costs["market"].isin(markets)
    filtered_costs = costs[cost_mask]

    daily = build_daily(filtered_trades, filtered_costs)
    by_asset = build_by_asset(filtered_trades, filtered_costs)

    total_net = daily["net_result"].sum()
    total_fees = daily["fees"].sum()
    total_irrf = daily["irrf"].sum()
    total_volume = daily["volume"].sum()
    total_operations = int(daily["operations"].sum())
    win_days = int((daily["net_result"] > 0).sum())
    total_days = len(daily)

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Resultado líquido", fmt_brl(total_net))
    col2.metric("Custos operacionais", fmt_brl(total_fees))
    col3.metric(
        "IRRF day trade",
        fmt_brl(total_irrf),
        help="Antecipação de imposto compensável — não é deduzida do resultado líquido.",
    )
    col4.metric("Volume operado", fmt_brl(total_volume))
    col5.metric("Dias positivos", f"{win_days}/{total_days}")

    colors = ["#2e7d32" if v >= 0 else "#c62828" for v in daily["net_result"]]
    fig = go.Figure()
    fig.add_bar(
        x=daily.index,
        y=daily["net_result"],
        marker_color=colors,
        name="Resultado do dia",
        yaxis="y",
    )
    fig.add_scatter(
        x=daily.index,
        y=daily["cumulative"],
        mode="lines+markers",
        name="Acumulado",
        line={"color": "#1565c0", "width": 2},
        yaxis="y",
    )
    fig.update_layout(
        barmode="relative",
        legend={"orientation": "h"},
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        yaxis={"title": "R$"},
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("Resultado por ativo")
    asset_table = by_asset.reset_index()
    asset_table = asset_table.rename(
        columns={
            "asset_name": "Ativo",
            "market": "Mercado",
            "operations": "Negociações",
            "volume": "Volume",
            "gross_result": "Resultado bruto",
            "allocated_costs": "Custos alocados",
            "net_result": "Resultado líquido",
        }
    )
    for col in ("Volume", "Resultado bruto", "Custos alocados", "Resultado líquido"):
        asset_table[col] = asset_table[col].map(fmt_brl)
    st.dataframe(asset_table, use_container_width=True, hide_index=True)

    st.subheader("Operações finalizadas")
    operations = build_closed_operations(filtered_trades, filtered_costs)
    for market in ("BOVESPA", "BMF"):
        block = operations[operations["market"] == market]
        if block.empty:
            continue
        table = block.copy()
        table["trading_date"] = table["trading_date"].dt.strftime("%d/%m/%Y")
        table = table.rename(
            columns={
                "trading_date": "Data",
                "asset_name": "Ativo",
                "quantity": "Qtd.",
                "direction": "C/V",
                "avg_price": "C. Médio",
                "final_price": "C. Final",
                "profitability": "Lucratividade",
                "result": "Resultado",
            }
        )
        table["Qtd."] = table["Qtd."].map(fmt_qty)
        for col in ("C. Médio", "C. Final"):
            table[col] = table[col].map(lambda v: "—" if pd.isna(v) else fmt_price(v))
        table["Lucratividade"] = table["Lucratividade"].map(
            lambda v: "—" if pd.isna(v) else fmt_pct(v)
        )
        table["Resultado"] = table["Resultado"].map(
            lambda v: "—" if pd.isna(v) else fmt_brl(v)
        )
        label = "Bovespa" if market == "BOVESPA" else "BM&F"
        st.markdown(f"**{label}**")
        st.dataframe(
            table[
                [
                    "Data",
                    "Ativo",
                    "Qtd.",
                    "C/V",
                    "C. Médio",
                    "C. Final",
                    "Lucratividade",
                    "Resultado",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.markdown(f"Subtotal **{label}:** {fmt_brl(block['result'].sum())}")
    st.markdown(f"**Total:** {fmt_brl(operations['result'].sum())}")

    with st.expander("Detalhamento diário"):
        daily_table = daily.reset_index()
        daily_table["trading_date"] = daily_table["trading_date"].dt.strftime("%d/%m/%Y")
        daily_table = daily_table.rename(
            columns={
                "trading_date": "Data",
                "operations": "Negociações",
                "volume": "Volume",
                "gross_result": "Resultado bruto",
                "fees": "Custos",
                "irrf": "IRRF",
                "net_result": "Resultado líquido",
                "cumulative": "Acumulado",
            }
        )
        for col in ("Volume", "Resultado bruto", "Custos", "IRRF", "Resultado líquido", "Acumulado"):
            daily_table[col] = daily_table[col].map(fmt_brl)
        st.dataframe(daily_table, use_container_width=True, hide_index=True)


def render_import():
    st.header("Importar notas de corretagem")
    uploads = st.file_uploader("Selecione os PDFs das notas", type="pdf", accept_multiple_files=True)

    if not uploads:
        st.caption("O importador é idêntico ao da CLI: arquivos já importados (SHA-256) são ignorados.")
        return

    for upload in uploads:
        try:
            parsed = parse_pdf(BytesIO(upload.getvalue()), file_name=upload.name)
        except Exception as exc:
            st.error(f"{upload.name}: {exc}")
            continue

        for note in parsed.notes:
            gross = sum(t.value for t in note.trades)
            liquid = note.costs.net_value if note.costs else None
            header = (
                f"{upload.name} — nota {note.note_number} · {note.trading_date.strftime('%d/%m/%Y')} · "
                f"{note.market} · {len(note.trades)} negociações · bruto {fmt_brl(float(gross))}"
                + (f" · líquido {fmt_brl(float(liquid))}" if liquid is not None else "")
            )
            with st.expander(header):
                rows = [
                    {
                        "C/V": t.side,
                        "Mercado": t.market_type,
                        "Ativo": t.asset_name,
                        "Qtd": t.quantity,
                        "Preço": t.price,
                        "Valor": t.value,
                    }
                    for t in note.trades
                ]
                st.dataframe(rows, use_container_width=True, hide_index=True)

    if st.button("Importar para o banco", type="primary"):
        with Session(get_engine()) as session:
            for upload in uploads:
                try:
                    result = import_bytes(session, upload.getvalue(), upload.name)
                except Exception as exc:
                    st.error(f"{upload.name}: {exc}")
                    continue
                if result.status == "skipped":
                    st.warning(f"{upload.name}: {result.message}")
                else:
                    skipped = f" ({result.skipped_notes} duplicadas)" if result.skipped_notes else ""
                    st.success(
                        f"{upload.name}: {result.notes} notas e {result.trades} negociações importadas{skipped}"
                    )
        load_trades.clear()
        load_costs.clear()


def main():
    st.title("📊 Day Trade — Notas de Corretagem")
    tab_overview, tab_import = st.tabs(["Visão geral", "Importar"])
    with tab_overview:
        render_overview()
    with tab_import:
        render_import()


if __name__ == "__main__":
    main()
