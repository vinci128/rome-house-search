"""Formattazione dei numeri in italiano: 350.000, non 350,000."""

from __future__ import annotations


def migliaia(numero: float | int | None) -> str:
    """`392000` -> `392.000` (separatore delle migliaia all'italiana)."""
    if numero is None:
        return "-"
    return f"{numero:,.0f}".replace(",", ".")


def euro(numero: float | int | None, con_simbolo: bool = True) -> str:
    """`350000` -> `350.000 €`."""
    testo = migliaia(numero)
    return f"{testo} €" if con_simbolo else testo
