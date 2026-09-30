"""Modello dati di un annuncio immobiliare.

L'annuncio contiene solo i fatti letti dalla scheda; i soldi (costo di
ristrutturazione, costo totale, punteggio, ammissibilità) stanno in
`valutazione.py`. Questo evita che lo stesso totale venga ricalcolato — e
ricalcolato in modo diverso — in tre punti diversi del codice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit

from .parsing import normalizza

CONDOTTI = ("ottimo", "parziale", "ristrutturare", "unknown")

ETICHETTE_CONDIZIONE = {
    "ottimo": "Pronto / ristrutturato",
    "parziale": "Parzialmente ristrutturato",
    "ristrutturare": "Da ristrutturare",
    "unknown": "Da verificare",
}

_PARAMETRI_TRACCIAMENTO = re.compile(
    r"^(utm_|ref$|gclid$|fbclid$|pagina$|pag$|source$)", re.IGNORECASE
)


@dataclass
class Annuncio:
    """Un annuncio come letto dalla scheda del portale."""

    titolo: str
    prezzo: int
    fonte: str
    url: str = ""
    indirizzo: str = ""
    zona: str = ""
    locali: int | None = None
    mq: int | None = None
    piano: str | None = None
    condizione: str = "unknown"
    segnali_condizione: list[str] = field(default_factory=list)

    @property
    def prezzo_al_mq(self) -> int | None:
        """Prezzo al mq arrotondato, se la superficie è nota."""
        if not self.mq:
            return None
        return round(self.prezzo / self.mq)

    @property
    def etichetta_condizione(self) -> str:
        return ETICHETTE_CONDIZIONE.get(self.condizione, self.condizione)

    @property
    def url_normalizzata(self) -> str:
        """URL ripulito da query e parametri di tracciamento (per il dedupe)."""
        if not self.url:
            return ""
        parti = urlsplit(self.url)
        if not parti.netloc:
            return self.url.rstrip("/")
        query = "&".join(
            p for p in parti.query.split("&")
            if p and not _PARAMETRI_TRACCIAMENTO.match(p.split("=")[0])
        )
        return urlunsplit((
            parti.scheme.lower() or "https",
            parti.netloc.lower().removeprefix("www."),
            parti.path.rstrip("/"),
            query,
            "",
        ))

    def chiave(self) -> str:
        """Chiave di deduplica: URL normalizzato, o contenuto dell'annuncio."""
        if self.url_normalizzata:
            return f"url:{self.url_normalizzata}"
        return "cont:" + "|".join((
            normalizza(self.titolo)[:60],
            str(self.prezzo),
            str(self.mq or ""),
        ))

    def to_dict(self) -> dict:
        return {
            "titolo": self.titolo,
            "prezzo": self.prezzo,
            "prezzo_al_mq": self.prezzo_al_mq,
            "locali": self.locali,
            "mq": self.mq,
            "piano": self.piano,
            "indirizzo": self.indirizzo,
            "url": self.url,
            "fonte": self.fonte,
            "zona": self.zona,
            "condizione": self.condizione,
            "segnali_condizione": list(self.segnali_condizione),
        }
