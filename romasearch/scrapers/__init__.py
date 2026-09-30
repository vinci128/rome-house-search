"""Registro dei portali e orchestrazione dello scraping."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import Config
from ..http import Limitatore, crea_sessione
from ..models import Annuncio
from . import casa, idealista, immobiliare, subito
from .base import link_ricerca as link_ricerca_del_sito

MODULI_SCRAPER = (immobiliare, idealista, casa)
MODULI_SOLO_LINK = (subito,)
MODULI = MODULI_SCRAPER + MODULI_SOLO_LINK


@dataclass
class Raccolta:
    """Esito dello scraping su tutti i portali."""

    annunci: list[Annuncio] = field(default_factory=list)
    problemi: list[str] = field(default_factory=list)
    per_sito: dict[str, int] = field(default_factory=dict)


def raccogli(cfg: Config, sessione=None) -> Raccolta:
    """Interroga tutti i portali per tutte le zone configurate."""
    sessione = sessione or crea_sessione(cfg)
    limitatore = Limitatore(cfg.pausa)
    raccolta = Raccolta()

    for zona in cfg.zone_risolte:
        for modulo in MODULI_SCRAPER:
            annunci, problemi = modulo.scrape(sessione, zona, cfg, limitatore)
            raccolta.annunci.extend(annunci)
            raccolta.problemi.extend(problemi)
            raccolta.per_sito[modulo.SITO] = raccolta.per_sito.get(modulo.SITO, 0) + len(annunci)

    # Lo stesso blocco ripetuto su più pagine è un solo problema.
    raccolta.problemi = list(dict.fromkeys(raccolta.problemi))
    return raccolta


def link_ricerca(cfg: Config) -> list[tuple[str, str]]:
    """Elenco (nome, url) dei link da aprire manualmente nel browser."""
    links: list[tuple[str, str]] = []
    for zona in cfg.zone_risolte:
        for modulo in MODULI:
            host = modulo.DOMINIO.removeprefix("www.")
            urls = link_ricerca_del_sito(modulo.url_ricerca, modulo.url_da_ristrutturare, zona, cfg)
            for indice, url in enumerate(urls):
                suffisso = " — da ristrutturare" if len(urls) > 1 and indice == 1 else ""
                links.append((f"{host} · {zona.etichetta}{suffisso}", url))
    return links
