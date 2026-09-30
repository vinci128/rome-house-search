"""Portale Idealista.it"""

from __future__ import annotations

import requests

from ..config import Config, Zona
from ..http import Limitatore
from ..models import Annuncio
from .base import ProfiloSito, link_ricerca, scarica_e_estrai

SITO = "idealista.it"
DOMINIO = "www.idealista.it"
BASE = f"https://{DOMINIO}/vendita-case/roma-rm"

PROFILO = ProfiloSito(
    sito=SITO,
    dominio=DOMINIO,
    card=("article.item", "[class*='listing-item']", "[data-adid]"),
    titolo=("a.item-link", "[class*='title']", "h2", "h3"),
    prezzo=("[class*='price']", ".price-row"),
    indirizzo=("[class*='location']", ".item-detail-location"),
)


def url_ricerca(zona: Zona, config: Config, pagina: int = 1) -> str:
    paginazione = f"&pagina={pagina}" if pagina > 1 else ""
    return (
        f"{BASE}/{zona.slug_idealista}/"
        f"?ordine=prezzo-asc"
        f"&prezzoMax={config.prezzo_max_ricerca}"
        f"&locali={config.query_locali}{paginazione}"
    )


def url_da_ristrutturare(zona: Zona, config: Config, pagina: int = 1) -> str:
    paginazione = f"&pagina={pagina}" if pagina > 1 else ""
    return (
        f"{BASE}/{zona.slug_idealista}/"
        f"?ordine=prezzo-asc"
        f"&prezzoMax={config.prezzo_max_da_ristrutturare}"
        f"&locali={config.query_locali}"
        f"&keywords=da+ristrutturare{paginazione}"
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
