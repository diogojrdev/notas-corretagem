from __future__ import annotations

import hashlib
from dataclasses import dataclass
from io import BytesIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from notas_corretagem.models import (
    BrokerageNote,
    BrokerageTrade,
    ImportedFile,
    NoteCosts,
)
from notas_corretagem.parser import ParsedNote, parse_pdf


@dataclass
class ImportResult:
    file_name: str
    status: str
    notes: int = 0
    trades: int = 0
    skipped_notes: int = 0
    message: str = ""


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_note_row(parsed: ParsedNote, file_row: ImportedFile) -> BrokerageNote:
    note = BrokerageNote(
        file_id=file_row.id,
        broker_name=parsed.broker_name,
        broker_cnpj=parsed.broker_cnpj,
        note_number=parsed.note_number,
        page=parsed.page,
        trading_date=parsed.trading_date,
        market=parsed.market,
        account_number=parsed.account_number,
        client_name=parsed.client_name,
        client_tax_id=parsed.client_tax_id,
    )
    note.trades = [
        BrokerageTrade(
            trading_date=parsed.trading_date,
            market_type=trade.market_type,
            asset_name=trade.asset_name,
            ticker=trade.ticker,
            side=trade.side,
            quantity=trade.quantity,
            price=trade.price,
            value=trade.value,
        )
        for trade in parsed.trades
    ]
    if parsed.costs is not None:
        note.costs = NoteCosts(**vars(parsed.costs))
    return note


def import_bytes(session: Session, data: bytes, file_name: str) -> ImportResult:
    digest = sha256_of(data)
    existing = session.scalar(select(ImportedFile).where(ImportedFile.file_sha256 == digest))
    if existing is not None:
        return ImportResult(file_name=file_name, status="skipped", message="arquivo já importado")

    parsed = parse_pdf(BytesIO(data), file_name=file_name)

    file_row = ImportedFile(file_name=file_name, file_sha256=digest)
    session.add(file_row)
    session.flush()

    imported_notes = imported_trades = skipped_notes = 0
    for parsed_note in parsed.notes:
        already = session.scalar(
            select(BrokerageNote).where(
                BrokerageNote.note_number == parsed_note.note_number,
                BrokerageNote.trading_date == parsed_note.trading_date,
                BrokerageNote.market == parsed_note.market,
            )
        )
        if already is not None:
            skipped_notes += 1
            continue
        session.add(_build_note_row(parsed_note, file_row))
        imported_notes += 1
        imported_trades += len(parsed_note.trades)

    session.add(file_row)
    session.commit()
    return ImportResult(
        file_name=file_name,
        status="imported",
        notes=imported_notes,
        trades=imported_trades,
        skipped_notes=skipped_notes,
    )


def import_file(session: Session, path) -> ImportResult:
    data = path.read_bytes()
    return import_bytes(session, data, path.name)
