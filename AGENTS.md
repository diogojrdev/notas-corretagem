# AGENTS.md

Instruções para agentes de LLM trabalhando neste repositório.

## O que é o projeto

Processamento de notas de corretagem de day trade da B3 com armazenamento em
PostgreSQL e painel de acompanhamento em Streamlit. O parser suporta os layouts
Sinacor BOVESPA (à vista e fracionário) e BMF (derivativos), lidos de PDFs
nativos digitais via camada de texto do pdfplumber (sem OCR).

Pipeline: PDF → parser (`src/notas_corretagem/parser/`) → importador
idempotente (`importer.py`, SHA-256 por arquivo + identidade por nota) →
PostgreSQL → cálculo e exibição no dashboard (`dashboard.py`).

## Regras de privacidade — repositório público

Este repositório é público. As regras abaixo não têm exceção:

- **Nunca versionar dados reais**: nomes de clientes, CPF/CNPJ, números de
  conta, operações reais, valores reais de notas. PDFs reais pertencem a
  `notas/`, que fica fora do versionamento via `.gitignore`. Validações com
  dados reais são feitas localmente, em memória, sem criar arquivos.
- **Testes usam somente dados sintéticos**. Os PDFs de `examples/` são 100%
  inventados e servem de modelo para novos casos de teste.
- **Nenhum comentário no código.** O código deve ser autoexplicativo; quando o
  estilo do módulo pedir docstring, que ela seja técnica, curta e neutra.
- **Neutralidade em código, testes, docs e commits**: nada de menções ao
  contexto ou motivação de mudanças, nem a relatórios, empresas, pessoas ou
  clientes externos. Mensagens de commit descrevem o quê, em termos técnicos
  (ex.: `feat: adicionar visão de operações finalizadas ao painel`).

## Metodologia de cálculo (invariáveis)

Qualquer mudança de cálculo precisa preservar estas regras:

- Convenção de sinais: débito (D) negativo, crédito (C) positivo. Em day trade,
  o somatório dos valores de um ativo no dia é o resultado bruto. No BMF o
  valor por negócio já é o ajuste (P&L da perna).
- Consistência por nota: `bruto − custos − IRRF = líquido` fecha com o
  "Líquido para" impresso na nota.
- Resultado líquido = bruto − custos operacionais. O IRRF de day trade é
  exibido separadamente (antecipação de imposto compensável) e **não** é
  deduzido do resultado.
- Custos são alocados por ativo e embutidos por perna proporcionalmente ao
  valor financeiro do dia.
- Operações finalizadas: pareamento compras×vendas do mesmo ativo no mesmo
  pregão em FIFO; lotes de compra consecutivos abertos e fechados pela mesma
  venda parcial são fundidos em um único pareamento. No BMF os preços médios
  exibidos são ajustes por contrato com sinal.
- Exibição em formato pt-BR (vírgula decimal), preços médios com 4 casas.

## Padrões de qualidade

- Python >= 3.12, type hints, `uv` como gerenciador de ambiente e dependências.
- Todo cálculo novo ou alterado vem com testes sintéticos em `tests/`; a suíte
  precisa passar (`uv run pytest`) antes de considerar o trabalho concluído.
- Validações numéricas contra o banco local podem ser feitas em sessão (script
  inline, sem arquivo), nunca como teste versionado com dados reais.
- Formatação e nomes seguem o estilo dos arquivos existentes; mudanças
  cirúrgicas, sem refactors além do escopo pedido.

## Comandos

```bash
docker compose up -d          # PostgreSQL 16 exclusivo do projeto (porta 5433)
uv sync                       # instala dependências
uv run alembic upgrade head   # cria/aplica migrações
uv run pytest                 # testes (parser + importer + dashboard)
uv run import-notas <caminho> # importa PDFs (arquivo ou diretório)
uv run streamlit run src/notas_corretagem/dashboard.py   # painel
```

Connection string em `.env` (ver `.env.example`); `.env` nunca é versionado.

## Limitações conhecidas do parser

Mantenha em mente ao estender:

- Custos BMF são parseados posicionalmente a partir do resumo financeiro
  (índices fixos); mudanças de layout quebram silenciosamente.
- O IRRF BOVESPA só é capturado pelo rótulo de day trade; IRRF de operações
  comuns não é extraído.
- Notas com múltiplas páginas: a unicidade `(note_number, trading_date,
  market)` não inclui a página — páginas 2+ de uma mesma nota seriam
  descartadas na importação.
- O cálculo assume operação quadrada no mesmo pregão (day trade puro); posição
  aberta aparece apenas como sobra informativa na visão de operações
  finalizadas.
