import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from notas_corretagem.importer import import_file
from notas_corretagem.models import Base, BrokerageNote, BrokerageTrade, ImportedFile

from tests.conftest import BMF_PDF, BOVESPA_PDF


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as sess:
        yield sess


def test_import_arquivos(session):
    result_bovespa = import_file(session, BOVESPA_PDF)
    result_bmf = import_file(session, BMF_PDF)

    assert result_bovespa.status == "imported"
    assert result_bovespa.notes == 2
    assert result_bovespa.trades == 12
    assert result_bmf.status == "imported"
    assert result_bmf.notes == 1
    assert result_bmf.trades == 3

    assert session.scalar(select(func.count(BrokerageNote.id))) == 3
    assert session.scalar(select(func.count(BrokerageTrade.id))) == 15
    assert session.scalar(select(func.count(ImportedFile.id))) == 2


def test_import_idempotente_por_sha256(session):
    import_file(session, BOVESPA_PDF)
    result = import_file(session, BOVESPA_PDF)

    assert result.status == "skipped"
    assert session.scalar(select(func.count(BrokerageNote.id))) == 2


def test_import_nota_duplicada_em_arquivo_diferente(session):
    import_file(session, BOVESPA_PDF)

    import copy
    from notas_corretagem.importer import import_bytes

    data = bytearray(BOVESPA_PDF.read_bytes())
    data.extend(b"%comment-trailing\n")
    result = import_bytes(session, bytes(data), "copia-modificada.pdf")

    assert result.status == "imported"
    assert result.notes == 0
    assert result.skipped_notes == 2
    assert session.scalar(select(func.count(BrokerageNote.id))) == 2
    assert session.scalar(select(func.count(ImportedFile.id))) == 2
