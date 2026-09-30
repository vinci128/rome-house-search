"""Portale Casa.it"""

from __future__ import annotations

import requests

from ..config import Config, Zona
from ..http import Limitatore
from ..models import Annuncio
from .base import ProfiloSito, link_ricerca, scarica_e_estrai

SITO = "casa.it"
DOMINIO = "www.casa.it"
BASE = f"https://{DOMINIO}/vendita/residenziale/roma"

PROFILO = ProfiloSito(
    sito=SITO,
    dominio=DOMINIO,
    # Ancorati a article/div per non agganciare i figli (titolo, prezzo).
    card=("article[class*='listing-card']", "div[class*='listing-card']",
          "[data-tracking-id]", "article"),
    titolo=("[class*='title']", "h2", "h3"),
    prezzo=("[class*='price']", "[class*='Price']"),
    indirizzo=("[class*='address']", "[class*='location']", "[class*='city']"),
)


def url_ricerca(zona: Zona, config: Config, pagina: int = 1) -> str:
    return (
        f"{BASE}/pag-{pagina}/"
        f"?locali_min={config.locali_minimi}"
        f"&prezzo_max={config.prezzo_max_ricerca}"
        f"&q={zona.ricerca_casa.replace(' ', '+')}"
    )


def url_da_ristrutturare(zona: Zona, config: Config, pagina: int = 1) -> str:
    return (
        f"{BASE}/pag-{pagina}/"
        f"?locali_min={config.locali_minimi}"
        f"&prezzo_max={config.prezzo_max_da_ristrutturare}"
        f"&q={zona.ricerca_casa.replace(' ', '+')}+da+ristrutturare"
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
