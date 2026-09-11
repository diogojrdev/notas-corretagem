from typing import IO

import pdfplumber


def extract_page_lines(source: str | IO[bytes]) -> list[list[str]]:
    with pdfplumber.open(source) as pdf:
        return [
            [line for line in (page.extract_text() or "").splitlines() if line.strip()]
            for page in pdf.pages
        ]
