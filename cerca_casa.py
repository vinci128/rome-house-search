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

from romasearch.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
