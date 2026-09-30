"""Portale immobiliare.it"""

from __future__ import annotations

import requests

from ..config import Config, Zona
from ..http import Limitatore
from ..models import Annuncio
from .base import ProfiloSito, link_ricerca, scarica_e_estrai

SITO = "immobiliare.it"
DOMINIO = "www.immobiliare.it"
BASE = f"https://{DOMINIO}/vendita-case"

PROFILO = ProfiloSito(
    sito=SITO,
    dominio=DOMINIO,
    card=(
        "li.nd-list__item",
        "article.in-listingCard",
        "li[data-testid='result-card']",
        "[class*='listing-card']",
        "[class*='ListingCard']",
    ),
    titolo=("[class*='title']", "h2", "h3"),
    prezzo=("[class*='price']", "[class*='Price']"),
    indirizzo=("[class*='address']", "[class*='location']", "[class*='Location']"),
)


def _locali_immobiliare(config: Config) -> str:
    """'3,4,5,6plus': tre valori espliciti e poi la coda aperta."""
    base = config.locali_minimi
    return ",".join([*(str(n) for n in range(base, base + 3)), f"{base + 3}plus"])


def url_ricerca(zona: Zona, config: Config, pagina: int = 1) -> str:
    url = (
        f"{BASE}/{zona.slug_immobiliare}/"
        f"?locali={_locali_immobiliare(config)}"
        f"&prezzoMassimo={config.prezzo_max_ricerca}"
    )
    if pagina > 1:
        url += f"&pag={pagina}"
    return url


def url_da_ristrutturare(zona: Zona, config: Config, pagina: int = 1) -> str:
    paginazione = f"&pag={pagina}" if pagina > 1 else ""
    return (
        f"{BASE}/{zona.slug_immobiliare}/"
        f"?locali={_locali_immobiliare(config)}"
        f"&prezzoMassimo={config.prezzo_max_da_ristrutturare}"
        f"&parole_chiave=da+ristrutturare{paginazione}"
    )


def scrape(
    sessione: requests.Session,
    zona: Zona,
    config: Config,
    limitatore: Limitatore | None = None,
) -> tuple[list[Annuncio], list[str]]:
    urls = link_ricerca(url_ricerca, url_da_ristrutturare, zona, config)
    return scarica_e_estrai(sessione, urls, PROFILO, zona, config,
                              limitatore=limitatore)
