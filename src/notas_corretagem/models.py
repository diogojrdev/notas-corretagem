from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ImportedFile(Base):
    __tablename__ = "imported_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    notes: Mapped[list[BrokerageNote]] = relationship(back_populates="file")


class BrokerageNote(Base):
    __tablename__ = "brokerage_notes"
    __table_args__ = (
        UniqueConstraint("note_number", "trading_date", "market", name="uq_note_identity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(
        ForeignKey("imported_files.id", ondelete="CASCADE"), index=True
    )
    broker_name: Mapped[str] = mapped_column(String(255))
    broker_cnpj: Mapped[str | None] = mapped_column(String(20))
    note_number: Mapped[str] = mapped_column(String(20), index=True)
    page: Mapped[int] = mapped_column(default=1)
    trading_date: Mapped[date] = mapped_column(Date, index=True)
    market: Mapped[str] = mapped_column(String(10))
    account_number: Mapped[str | None] = mapped_column(String(20))
    client_name: Mapped[str | None] = mapped_column(String(255))
    client_tax_id: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    file: Mapped[ImportedFile] = relationship(back_populates="notes")
    trades: Mapped[list[BrokerageTrade]] = relationship(
        back_populates="note", cascade="all, delete-orphan"
    )
    costs: Mapped[NoteCosts | None] = relationship(
        back_populates="note", cascade="all, delete-orphan", uselist=False
    )


class BrokerageTrade(Base):
    __tablename__ = "brokerage_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(
        ForeignKey("brokerage_notes.id", ondelete="CASCADE"), index=True
    )
    trading_date: Mapped[date] = mapped_column(Date, index=True)
    market_type: Mapped[str] = mapped_column(String(30))
    asset_name: Mapped[str] = mapped_column(String(255))
    ticker: Mapped[str | None] = mapped_column(String(20), index=True)
    side: Mapped[str] = mapped_column(String(1))
    quantity: Mapped[int]
    price: Mapped[Decimal] = mapped_column(Numeric(14, 6))
    value: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    note: Mapped[BrokerageNote] = relationship(back_populates="trades")


class NoteCosts(Base):
    __tablename__ = "brokerage_note_costs"
    __table_args__ = (UniqueConstraint("note_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    note_id: Mapped[int] = mapped_column(
        ForeignKey("brokerage_notes.id", ondelete="CASCADE")
    )
    net_operations_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    settlement_fee: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    registration_fee: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    clearing_total: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    emoluments: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    brokerage_fee: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    iss: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    irrf: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    other_fees: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    net_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))

    note: Mapped[BrokerageNote] = relationship(back_populates="costs")
