"""Subito.it: solo link da aprire a mano (niente scraping)."""

from __future__ import annotations

from ..config import Config, Zona

SITO = "subito.it"
DOMINIO = "www.subito.it"
BASE = f"https://{DOMINIO}/annunci-lazio/vendita/appartamenti/roma"


def url_ricerca(zona: Zona, config: Config, pagina: int = 1) -> str:  # noqa: ARG001
    return (
        f"{BASE}/{zona.nome.replace('-', '+')}/"
        f"?locali_min={config.locali_minimi}"
        f"&prezzo_max={config.prezzo_max_ricerca}"
    )


def url_da_ristrutturare(zona: Zona, config: Config, pagina: int = 1) -> str:  # noqa: ARG001
    return (
        f"{BASE}/{zona.nome.replace('-', '+')}/"
        f"?locali_min={config.locali_minimi}"
        f"&prezzo_max={config.prezzo_max_da_ristrutturare}"
        f"&q=da+ristrutturare"
    )
