# notas-corretagem

Processamento de notas de corretagem (day trade) com armazenamento em PostgreSQL
e painel de acompanhamento em Streamlit. Suporta os layouts BOVESPA (ações,
mercado à vista e fracionário) e BMF (derivativos).

As notas são PDFs nativos digitais, portanto a extração usa a camada de texto
via pdfplumber — sem OCR, com precisão exata sobre preços e valores.

## Layouts suportados

O parser foi construído sobre o layout Sinacor — o padrão usado pela maioria
das corretoras B3 — nas versões BOVESPA e BMF. Como cada corretora renderiza
esse padrão com pequenas variações (ordem das linhas, rótulos do resumo
financeiro), notas de outras corretoras podem exigir ajustes nas expressões
regulares de `src/notas_corretagem/parser/nota.py`.

A pasta `examples/` contém notas fictícias de exemplo (dados 100% inventados)
que podem ser usadas para testar o import e o painel sem dados reais. Para
regenerá-las:

```bash
uv run python scripts/generate_example_notas.py
```

Notas reais devem ficar em `notas/` (fora do versionamento via `.gitignore`,
pois contêm dados pessoais).

## Setup

```bash
docker compose up -d          # PostgreSQL 16 exclusivo do projeto (porta 5433)
uv sync                       # instala dependências
uv run alembic upgrade head   # cria as tabelas
```

A connection string fica em `.env` (ver `.env.example`).

## Uso

```bash
uv run import-notas examples/                 # importa PDFs (arquivo ou diretório)
uv run streamlit run src/notas_corretagem/dashboard.py   # painel
uv run pytest                                 # testes (parser + importer + dashboard)
```

O painel tem duas abas:

- **Visão geral** — filtros de período/mercado/ativo, resultado líquido, custos
  operacionais, IRRF, volume, dias positivos, gráfico diário + acumulado e
  resultado por ativo (custos alocados proporcionalmente ao volume do dia).
- **Importar** — upload de PDFs com preview das negociações antes de gravar.

## Modelo de dados

| tabela | conteúdo |
|---|---|
| `imported_files` | arquivos processados (SHA-256 único — idempotência) |
| `brokerage_notes` | uma nota por página (número, pregão, corretora, mercado) |
| `brokerage_trades` | negociações (ativo, C/V, quantidade, preço, valor com sinal) |
| `brokerage_note_costs` | custos da nota (liquidação, registro, emolumentos, ISS, IRRF, líquido) |

Convenção de sinais: débito (D) negativo, crédito (C) positivo — em day trade o
somatório dos valores de um ativo no dia é o resultado bruto. No BMF o valor por
negócio já é o ajuste (P&L da perna), mesma convenção.

A consistência é verificável por nota: `bruto − custos − IRRF = líquido`.

## Estrutura

```
src/notas_corretagem/
├── config.py        # DATABASE_URL (pydantic-settings)
├── models.py        # SQLAlchemy
├── parser/          # extractor pdfplumber + parser BOVESPA/BMF
├── importer.py      # inserção idempotente
├── cli.py           # import-notas
└── dashboard.py     # Streamlit
migrations/          # Alembic
scripts/             # gerador dos PDFs de exemplo
examples/            # notas fictícias para testes e demonstração
tests/               # parser, importer e dashboard validados contra os PDFs de exemplo
```
