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


def build_daily(trades: pd.DataFrame, costs: pd.DataFrame) -> pd.DataFrame:
    abs_value = trades["value"].abs()
    gross = trades.groupby("trading_date")["value"].sum().to_frame("gross_result")
    volume = abs_value.groupby(trades["trading_date"]).sum().to_frame("volume")
    operations = trades.groupby("trading_date").size().to_frame("operations")

    daily_costs = costs.groupby("trading_date")[["fees", "irrf"]].sum()

    daily = gross.join(volume).join(operations).join(daily_costs, how="left").fillna(0.0)
    daily["net_result"] = daily["gross_result"] - daily["fees"] - daily["irrf"]
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
    daily_fees = costs.groupby("trading_date")[["fees", "irrf"]].sum()

    allocated = []
    for (day, asset), vol in daily_asset_volume.items():
        day_fees = daily_fees.loc[day].sum() if day in daily_fees.index else 0.0
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
    col3.metric("IRRF day trade", fmt_brl(total_irrf))
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
