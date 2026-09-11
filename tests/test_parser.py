from decimal import Decimal

from notas_corretagem.parser import parse_pdf

from tests.conftest import BMF_PDF, BOVESPA_PDF


def test_bovespa_pdf_contem_duas_notas():
    parsed = parse_pdf(str(BOVESPA_PDF))
    assert len(parsed.notes) == 2
    assert all(note.market == "BOVESPA" for note in parsed.notes)


def test_bovespa_primeira_nota_cabecalho():
    note = parse_pdf(str(BOVESPA_PDF)).notes[0]
    assert note.note_number == "100001"
    assert note.page == 1
    assert str(note.trading_date) == "2026-08-26"
    assert note.broker_name == "CORRETORA EXEMPLO LTDA"
    assert note.broker_cnpj == "00.000.000/0001-00"
    assert note.account_number == "123456-7"
    assert note.client_name == "CLIENTE EXEMPLO DA SILVA"
    assert note.client_tax_id == "123.456.789-00"


def test_bovespa_primeira_nota_trades():
    note = parse_pdf(str(BOVESPA_PDF)).notes[0]
    assert len(note.trades) == 6

    first = note.trades[0]
    assert first.side == "C"
    assert first.market_type == "VISTA"
    assert first.asset_name == "EMPRESA ALFA PN N1"
    assert first.quantity == 200
    assert first.price == Decimal("5.15")
    assert first.value == Decimal("-1030.00")

    assert sum(t.value for t in note.trades) == Decimal("34.00")


def test_bovespa_segunda_nota_trades():
    note = parse_pdf(str(BOVESPA_PDF)).notes[1]
    assert note.note_number == "100002"
    assert str(note.trading_date) == "2026-08-31"
    assert len(note.trades) == 6
    assert sum(t.value for t in note.trades) == Decimal("120.00")


def test_bovespa_custos_e_consignancia():
    for note in parse_pdf(str(BOVESPA_PDF)).notes:
        costs = note.costs
        gross = sum(t.value for t in note.trades)
        assert costs.net_operations_value == gross
        fees = sum(
            abs(x)
            for x in (
                costs.settlement_fee,
                costs.registration_fee,
                costs.emoluments,
                costs.brokerage_fee,
                costs.iss,
                costs.other_fees,
            )
            if x is not None
        )
        assert gross - fees - abs(costs.irrf) == costs.net_value

    first = parse_pdf(str(BOVESPA_PDF)).notes[0].costs
    assert first.settlement_fee == Decimal("-0.59")
    assert first.emoluments == Decimal("-0.16")
    assert first.brokerage_fee == Decimal("-0.49")
    assert first.iss == Decimal("-0.03")
    assert first.irrf == Decimal("-0.34")
    assert first.clearing_total == Decimal("-0.59")
    assert first.net_value == Decimal("32.39")


def test_bmf_nota_completa():
    parsed = parse_pdf(str(BMF_PDF))
    assert len(parsed.notes) == 1
    note = parsed.notes[0]

    assert note.market == "BMF"
    assert note.note_number == "200001"
    assert str(note.trading_date) == "2026-08-27"
    assert note.broker_name == "CORRETORA EXEMPLO LTDA"
    assert note.account_number == "123456"

    assert len(note.trades) == 3
    first = note.trades[0]
    assert first.side == "V"
    assert first.market_type == "DAY TRADE"
    assert first.asset_name == "XYZ Q26"
    assert first.ticker == "XYZQ26"
    assert first.quantity == 5
    assert first.price == Decimal("109.1200")
    assert first.value == Decimal("-22.70")

    assert sum(t.value for t in note.trades) == Decimal("26.20")


def test_bmf_custos_e_consignancia():
    note = parse_pdf(str(BMF_PDF)).notes[0]
    costs = note.costs
    assert costs.net_operations_value == Decimal("26.20")
    assert costs.registration_fee == Decimal("-1.90")
    assert costs.emoluments == Decimal("-1.10")
    assert costs.brokerage_fee == Decimal("-7.70")
    assert costs.other_fees == Decimal("-0.57")
    assert costs.iss == Decimal("-0.03")
    assert costs.irrf == Decimal("-0.26")
    assert costs.net_value == Decimal("14.64")

    gross = sum(t.value for t in note.trades)
    fees = sum(
        abs(x)
        for x in (
            costs.registration_fee,
            costs.emoluments,
            costs.brokerage_fee,
            costs.iss,
            costs.other_fees,
        )
        if x is not None
    )
    assert gross - fees - abs(costs.irrf) == costs.net_value
