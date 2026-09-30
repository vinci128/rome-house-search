#!/usr/bin/env python3
"""Cerca casa a Roma — punto d'ingresso.

Uso rapido:
    python3 cerca_casa.py                      # 3+ locali a Torrino entro 350.000€
    python3 cerca_casa.py --links              # link da aprire nel browser
    python3 cerca_casa.py --budget 250000 --zona eur --zona montesacro

Tutte le opzioni: python3 cerca_casa.py --help
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ISTRUZIONI = (
    "Dipendenze mancanti: {mancanti}.\n"
    "Installale con uno di questi comandi:\n"
    "    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt\n"
    "    uv venv && uv pip install -r requirements.txt\n"
    "\n"
    "Poi rilancia con il Python del virtualenv:\n"
    "    .venv/bin/python cerca_casa.py ...\n"
    "\n"
    "Nel dubbio: --links funziona anche senza dipendenze installate."
)


def _importa_cli() -> "object":
    """Importa la CLI spiegando come installare le dipendenze se mancano.

    Tipico: `python3 cerca_casa.py` con il Python di sistema invece di quello
    del virtualenv, che porta a un ModuleNotFoundError incomprensibile.
    """
    try:
        from romasearch.cli import main  # noqa: PLC0415 - deve poter fallire qui
    except ModuleNotFoundError as exc:
        if exc.name not in ("requests", "bs4", "lxml", "soupsieve"):
            raise
        print(f"\n{exc.name} non è installato in questo Python.\n", file=sys.stderr)
        print(ISTRUZIONI.format(mancanti=exc.name), file=sys.stderr)
        print(f"(Python in uso: {sys.executable})", file=sys.stderr)
        sys.exit(2)
    return main


if __name__ == "__main__":
    raise SystemExit(_importa_cli()())
