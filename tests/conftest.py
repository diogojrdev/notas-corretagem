from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"
BOVESPA_PDF = EXAMPLES_DIR / "exemplo_bovespa.pdf"
BMF_PDF = EXAMPLES_DIR / "exemplo_bmf.pdf"

pytestmark = pytest.mark.skipif(
    not BOVESPA_PDF.exists() or not BMF_PDF.exists(),
    reason="PDFs de exemplo não encontrados (gere com scripts/generate_example_notas.py)",
)
