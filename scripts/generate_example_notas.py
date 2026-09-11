"""Gera os PDFs de exemplo usados nos testes e como amostra dos layouts.

Todos os dados são fictícios (corretora, cliente, conta, CPF/CNPJ e ativos).
Os layouts BOVESPA e BMF seguem o padrão Sinacor: uma nota por página,
negociações no corpo do documento e resumo financeiro ao final.

Uso: uv run python scripts/generate_example_notas.py
"""

from __future__ import annotations

from pathlib import Path

from fpdf import FPDF

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"

BROKER_NAME = "CORRETORA EXEMPLO LTDA"
BROKER_CNPJ = "00.000.000/0001-00"
BROKER_PHONE = "Fone: (00) 0000-0000"
CLIENT_NAME = "CLIENTE EXEMPLO DA SILVA"
CLIENT_CPF = "123.456.789-00"
ACCOUNT_BOVESPA = "123456-7"
ACCOUNT_BMF = "123456"

BOVESPA_NOTES = [
    {
        "number": "100001",
        "page": "1",
        "date": "26/08/2026",
        "trades": [
            ("C", "VISTA", "EMPRESA ALFA PN N1", "200", "5,15", "1.030,00", "D"),
            ("V", "VISTA", "EMPRESA ALFA PN N1", "200", "5,20", "1.040,00", "C"),
            ("C", "FRACIONARIO", "EMPRESA BETA ON N2", "100", "10,00", "1.000,00", "D"),
            ("V", "FRACIONARIO", "EMPRESA BETA ON N2", "100", "10,09", "1.009,00", "C"),
            ("C", "VISTA", "EMPRESA GAMA ON NM", "300", "20,00", "6.000,00", "D"),
            ("V", "VISTA", "EMPRESA GAMA ON NM", "300", "20,05", "6.015,00", "C"),
        ],
        "costs": [
            "Valor líquido das operações 34,00 C",
            "Taxa de liquidação 0,59 D",
            "Total CBLC 0,59 D",
            "Emolumentos 0,16 D",
            "Execução 0,49 D",
            "ISS 0,03 D",
            "IRRF Day Trade: Base R$ 34,00 Projeção R$ 0,34",
            "Líquido para 27/08/2026 32,39 C",
        ],
    },
    {
        "number": "100002",
        "page": "1",
        "date": "31/08/2026",
        "trades": [
            ("C", "VISTA", "EMPRESA DELTA ON N1", "100", "30,00", "3.000,00", "D"),
            ("V", "VISTA", "EMPRESA DELTA ON N1", "100", "30,50", "3.050,00", "C"),
            ("C", "VISTA", "EMPRESA EPSILON PN N2", "200", "25,00", "5.000,00", "D"),
            ("V", "VISTA", "EMPRESA EPSILON PN N2", "200", "25,25", "5.050,00", "C"),
            ("C", "FRACIONARIO", "EMPRESA ZETA ON NM", "400", "9,00", "3.600,00", "D"),
            ("V", "FRACIONARIO", "EMPRESA ZETA ON NM", "400", "9,05", "3.620,00", "C"),
        ],
        "costs": [
            "Valor líquido das operações 120,00 C",
            "Taxa de liquidação 0,62 D",
            "Total CBLC 0,62 D",
            "Emolumentos 0,19 D",
            "Execução 0,49 D",
            "ISS 0,03 D",
            "IRRF Day Trade: Base R$ 120,00 Projeção R$ 1,20",
            "Líquido para 01/09/2026 117,47 C",
        ],
    },
]

# (side, asset, expiry, quantity, price, market, value, dc, adjustment)
BMF_TRADES = [
    ("V", "XYZ Q26", "01/10/2026", "5", "109,1200", "DAY TRADE", "22,70", "D", "4,54"),
    ("C", "XYZ Q26", "01/10/2026", "5", "109,2440", "DAY TRADE", "60,00", "C", "12,00"),
    ("V", "XYZ Q26", "01/10/2026", "5", "109,3120", "DAY TRADE", "11,10", "D", "2,22"),
]

# Resumo financeiro BMF: resumo, taxas, despesas e totais (linhas só de valores).
BMF_VALUE_LINES = [
    "0,00 0,00 0,00 0,00 26,20 C",
    "0,00 0,26 0,00 1,90 1,10 D",
    "0,57 0,03 0,00 0,00",
    "0,00 0,00 7,70 D 14,64 C",
]


def _bovespa_page(note: dict) -> list[str]:
    lines = [
        BROKER_NAME,
        f"CNPJ: {BROKER_CNPJ}",
        f"{note['number']} {note['page']} {note['date']}",
        BROKER_NAME,
        "Clientes",
        f"{ACCOUNT_BOVESPA} {CLIENT_NAME} {CLIENT_CPF}",
        "Assessor: 0000",
        "Negociações realizadas",
        "C/V Mercado Especificação do título Quant. Preço (R$) Valor (R$) D/C",
    ]
    lines += [
        f"B3 BF SOMA {side} {market} {asset} {qty} {price} {value} {dc}"
        for side, market, asset, qty, price, value, dc in note["trades"]
    ]
    lines += ["Resumo financeiro"]
    lines += note["costs"]
    return lines


def _bmf_page() -> list[str]:
    return [
        BROKER_NAME,
        f"CNPJ: {BROKER_CNPJ}",
        "200001 1 27/08/2026",
        BROKER_NAME,
        "Clientes",
        f"{CLIENT_NAME} {CLIENT_CPF}",
        ACCOUNT_BMF,
        f"{BROKER_NAME} {BROKER_PHONE}",
        "Mercadoria Vencimento D/C",
        "C/V Mercadoria Vencimento Quant. Preço Mercado Valor D/C Ajuste",
        *[
            f"{side} {asset} {expiry} {qty} {price} {market} {value} {dc} {adjustment}"
            for side, asset, expiry, qty, price, market, value, dc, adjustment in BMF_TRADES
        ],
        "Resumo dos negócios",
        *BMF_VALUE_LINES,
    ]


def _write_pdf(path: Path, pages: list[list[str]]) -> None:
    pdf = FPDF()
    pdf.set_auto_page_break(False)
    for lines in pages:
        pdf.add_page()
        pdf.set_font("helvetica", size=9)
        for text in lines:
            pdf.cell(0, 5, text, new_x="LMARGIN", new_y="NEXT")
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(path)


def main() -> None:
    _write_pdf(EXAMPLES_DIR / "exemplo_bovespa.pdf", [_bovespa_page(n) for n in BOVESPA_NOTES])
    _write_pdf(EXAMPLES_DIR / "exemplo_bmf.pdf", [_bmf_page()])
    print(f"PDFs gerados em {EXAMPLES_DIR}")


if __name__ == "__main__":
    main()
