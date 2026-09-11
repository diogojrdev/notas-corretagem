from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import IO

from notas_corretagem.parser.extractor import extract_page_lines

NOTE_HEADER_RE = re.compile(r"^([\d.]+)\s+(\d+)\s+(\d{2}/\d{2}/\d{4})$")
CNPJ_RE = re.compile(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}")
CLIENT_BOVESPA_RE = re.compile(r"^(\d{5,10}-\d)\s+(.+?)\s+(\d{3}\.\d{3}\.\d{3}-\d{2})$")
CLIENT_BMF_RE = re.compile(r"^([A-Z].+?)\s+(\d{3}\.\d{3}\.\d{3}-\d{2})$")
ACCOUNT_ONLY_RE = re.compile(r"^\d{6,10}$")

TRADE_BOVESPA_RE = re.compile(
    r"^B3\s+\S+\s+\S+\s+([CV])\s+(\S+)\s+(.+?)\s+(\d+)\s+([\d.,]+)\s+([\d.,]+)\s+([DC])$"
)
TRADE_BMF_RE = re.compile(
    r"^([CV])\s+(.+?)\s+(\d{2}/\d{2}/\d{4})\s+(\d+)\s+([\d.,]+)\s+(.+?)\s+([\d.,]+)\s+([DC])\s+([\d.,]+)$"
)

BOVESPA_COST_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("net_operations_value", re.compile(r"\bvalor liquido das operacoes\s+([\d.,]+)\s+([dc])")),
    ("settlement_fee", re.compile(r"\btaxa de liquidacao\s+([\d.,]+)\s+([dc])")),
    ("registration_fee", re.compile(r"\btaxa de registro\s+([\d.,]+)\s+([dc])")),
    ("clearing_total", re.compile(r"\btotal cblc\s+([\d.,]+)\s+([dc])")),
    ("emoluments", re.compile(r"\bemolumentos\s+([\d.,]+)\s+([dc])")),
    ("brokerage_fee", re.compile(r"\bexecucao\s+([\d.,]+)\s+([dc])")),
    ("other_fees", re.compile(r"\boutras\s+([\d.,]+)\s+([dc])")),
    ("net_value", re.compile(r"\bliquido para\s+\d{2}/\d{2}/\d{4}\s+([\d.,]+)\s+([dc])")),
    ("iss", re.compile(r"\biss\b\D*?([\d.,]+)(?:\s+([dc]))?$")),
]
BOVESPA_IRRF_RE = re.compile(r"\birrf day.?trade:\s*base r\$\s*[\d.,]+\s*projecao r\$\s*([\d.,]+)")

BMF_VALUE_LINE_RE = re.compile(r"^(?:[\d.,]+|[DC])(?:\s+(?:[\d.,]+|[DC]))+$")
BMF_VALUE_TOKEN_RE = re.compile(r"([\d.,]+)\s*([DC])?")


@dataclass
class ParsedTrade:
    market_type: str
    asset_name: str
    ticker: str | None
    side: str
    quantity: int
    price: Decimal
    value: Decimal


@dataclass
class ParsedCosts:
    net_operations_value: Decimal | None = None
    settlement_fee: Decimal | None = None
    registration_fee: Decimal | None = None
    clearing_total: Decimal | None = None
    emoluments: Decimal | None = None
    brokerage_fee: Decimal | None = None
    iss: Decimal | None = None
    irrf: Decimal | None = None
    other_fees: Decimal | None = None
    net_value: Decimal | None = None


@dataclass
class ParsedNote:
    note_number: str
    page: int
    trading_date: date
    market: str
    broker_name: str
    broker_cnpj: str | None
    account_number: str | None
    client_name: str | None
    client_tax_id: str | None
    trades: list[ParsedTrade] = field(default_factory=list)
    costs: ParsedCosts | None = None


@dataclass
class ParsedFile:
    file_name: str
    notes: list[ParsedNote] = field(default_factory=list)


def parse_money(raw: str) -> Decimal:
    return Decimal(raw.replace(".", "").replace(",", "."))


def signed(raw: str, flag: str | None, default: str = "-") -> Decimal:
    value = parse_money(raw)
    effective = (flag or default).upper()
    return value if effective == "C" else -value


def _normalize(line: str) -> str:
    without_soft_hyphen = line.replace("\u00ad", "")
    decomposed = unicodedata.normalize("NFKD", without_soft_hyphen)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold()


def _parse_brl_date(raw: str) -> date:
    return datetime.strptime(raw, "%d/%m/%Y").date()


def _parse_header(lines: list[str]) -> tuple[str, int, date, int]:
    for idx, line in enumerate(lines):
        match = NOTE_HEADER_RE.match(line)
        if match:
            note_number = match.group(1).replace(".", "")
            page = int(match.group(2))
            trading_date = _parse_brl_date(match.group(3))
            return note_number, page, trading_date, idx
    raise ValueError("cabeçalho da nota (número, folha, data pregão) não encontrado")


def _parse_bovespa_client(lines: list[str]) -> tuple[str | None, str | None, str | None]:
    for line in lines:
        match = CLIENT_BOVESPA_RE.match(line)
        if match:
            return match.group(1), match.group(2).strip(), match.group(3)
    return None, None, None


def _parse_bmf_client(lines: list[str]) -> tuple[str | None, str | None, str | None]:
    name = tax_id = account = None
    for line in lines:
        match = CLIENT_BMF_RE.match(line)
        if match and name is None:
            name, tax_id = match.group(1).strip(), match.group(2)
        if account is None and ACCOUNT_ONLY_RE.match(line):
            account = line
    return account, name, tax_id


def _parse_bovespa_costs(lines: list[str]) -> ParsedCosts:
    costs = ParsedCosts()
    for raw_line in lines:
        line = _normalize(raw_line)
        irrf_match = BOVESPA_IRRF_RE.search(line)
        if irrf_match:
            costs.irrf = -parse_money(irrf_match.group(1))
            continue
        for field_name, pattern in BOVESPA_COST_PATTERNS:
            if field_name in ("iss",) and costs.iss is not None:
                continue
            match = pattern.search(line)
            if match and getattr(costs, field_name) is None:
                setattr(costs, field_name, signed(match.group(1), match.group(2)))
    return costs


def _bmf_value_lines(lines: list[str]) -> list[list[tuple[str, str | None]]]:
    result = []
    for line in lines:
        if BMF_VALUE_LINE_RE.match(line):
            tokens = [(raw, flag or None) for raw, flag in BMF_VALUE_TOKEN_RE.findall(line)]
            if len(tokens) >= 4:
                result.append(tokens)
    return result


def _parse_bmf_costs(lines: list[str]) -> ParsedCosts:
    value_lines = _bmf_value_lines(lines)
    if len(value_lines) < 4:
        raise ValueError("resumo financeiro BMF não encontrado")

    summary, fees, expenses, totals = value_lines[:4]

    costs = ParsedCosts()
    value, flag = summary[-1]
    costs.net_operations_value = signed(value, flag)
    costs.irrf = -parse_money(fees[1][0])
    costs.registration_fee = -parse_money(fees[3][0])
    costs.emoluments = signed(fees[4][0], fees[4][1])
    costs.other_fees = -parse_money(expenses[0][0])
    costs.iss = -parse_money(expenses[1][0])
    costs.brokerage_fee = signed(totals[2][0], totals[2][1])
    costs.net_value = signed(totals[-1][0], totals[-1][1])
    return costs


def _parse_bovespa_trades(lines: list[str]) -> list[ParsedTrade]:
    trades = []
    for line in lines:
        match = TRADE_BOVESPA_RE.match(line)
        if match:
            side, market_type, asset_name, quantity, price, value, dc = match.groups()
            trades.append(
                ParsedTrade(
                    market_type=market_type,
                    asset_name=asset_name,
                    ticker=None,
                    side=side,
                    quantity=int(quantity),
                    price=parse_money(price),
                    value=signed(value, dc),
                )
            )
    return trades


def _parse_bmf_trades(lines: list[str]) -> list[ParsedTrade]:
    trades = []
    for line in lines:
        match = TRADE_BMF_RE.match(line)
        if match:
            side, asset_name, _, quantity, price, market_type, value, dc, _ = match.groups()
            trades.append(
                ParsedTrade(
                    market_type=market_type,
                    asset_name=asset_name,
                    ticker=asset_name.replace(" ", ""),
                    side=side,
                    quantity=int(quantity),
                    price=parse_money(price),
                    value=signed(value, dc),
                )
            )
    return trades


def _find_cnpj(lines: list[str]) -> str | None:
    for line in lines:
        match = CNPJ_RE.search(line)
        if match:
            return match.group(0)
    return None


def _parse_bovespa_page(lines: list[str]) -> ParsedNote:
    note_number, page, trading_date, header_idx = _parse_header(lines)
    account, client_name, client_tax_id = _parse_bovespa_client(lines)
    trades = _parse_bovespa_trades(lines)
    if not trades:
        raise ValueError(f"nota {note_number}: nenhuma negociação BOVESPA reconhecida")
    return ParsedNote(
        note_number=note_number,
        page=page,
        trading_date=trading_date,
        market="BOVESPA",
        broker_name=lines[header_idx + 1].strip(),
        broker_cnpj=_find_cnpj(lines),
        account_number=account,
        client_name=client_name,
        client_tax_id=client_tax_id,
        trades=trades,
        costs=_parse_bovespa_costs(lines),
    )


def _parse_bmf_page(lines: list[str]) -> ParsedNote:
    note_number, page, trading_date, header_idx = _parse_header(lines)
    account, client_name, client_tax_id = _parse_bmf_client(lines)
    trades = _parse_bmf_trades(lines)
    if not trades:
        raise ValueError(f"nota {note_number}: nenhuma negociação BMF reconhecida")

    broker_name = ""
    for line in lines:
        if "Fone:" in line:
            broker_name = line.split("Fone:")[0].strip()
            break

    return ParsedNote(
        note_number=note_number,
        page=page,
        trading_date=trading_date,
        market="BMF",
        broker_name=broker_name,
        broker_cnpj=_find_cnpj(lines),
        account_number=account,
        client_name=client_name,
        client_tax_id=client_tax_id,
        trades=trades,
        costs=_parse_bmf_costs(lines),
    )


def _parse_page(lines: list[str]) -> ParsedNote:
    joined = "\n".join(lines)
    if "Especificação do título" in joined:
        return _parse_bovespa_page(lines)
    if "Mercadoria" in joined and "Vencimento" in joined:
        return _parse_bmf_page(lines)
    raise ValueError("layout de nota não reconhecido (nem BOVESPA nem BMF)")


def parse_pdf(source: str | IO[bytes], file_name: str = "") -> ParsedFile:
    pages = extract_page_lines(source)
    notes = [_parse_page(lines) for lines in pages]
    return ParsedFile(file_name=file_name, notes=notes)
