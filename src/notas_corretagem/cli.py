import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from notas_corretagem.config import get_settings
from notas_corretagem.importer import ImportResult, import_file


def collect_pdfs(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.pdf"))
    raise FileNotFoundError(f"caminho não encontrado: {path}")


def print_result(result: ImportResult) -> None:
    if result.status == "skipped":
        print(f"[skip]    {result.file_name}: {result.message}")
    elif result.status == "error":
        print(f"[erro]    {result.file_name}: {result.message}")
    else:
        skipped = f" ({result.skipped_notes} notas duplicadas)" if result.skipped_notes else ""
        print(f"[ok]      {result.file_name}: {result.notes} notas, {result.trades} negociações{skipped}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="import-notas", description="Importa notas de corretagem (PDF) para o banco"
    )
    parser.add_argument("path", help="arquivo PDF ou diretório com PDFs")
    args = parser.parse_args(argv)

    pdfs = collect_pdfs(Path(args.path))
    if not pdfs:
        print("nenhum PDF encontrado")
        return 1

    engine = create_engine(get_settings().sqlalchemy_url)
    failures = 0
    with Session(engine) as session:
        for pdf in pdfs:
            try:
                result = import_file(session, pdf)
            except Exception as exc:
                result = ImportResult(file_name=pdf.name, status="error", message=str(exc))
                failures += 1
            print_result(result)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
