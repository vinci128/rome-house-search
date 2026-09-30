"""Accesso HTTP educato ai portali: sessione, retry con backoff, rate limit.

I portali immobiliari hanno protezioni anti-bot. Non le aggiriamo: se una
richiesta viene bloccata lo diciamo chiaramente e continuiamo con gli altri
siti, invece di spacciare uno zero risultati per una ricerca senza esito.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import requests

from .config import Config

# Indicatori tipici di una pagina di blocco, da distinguere da "zero risultati".
SEGNALI_ANTIBOT = (
    "captcha",
    "verifica che sei un umano",
    "verifica di essere un umano",
    "check your browser",
    "accesso negato",
    "sei stato bloccato",
    "richiesta rifiutata",
    "abuse",
    "cf-challenge",
    "enable javascript and cookies",
    "ray id",
)


class ErroreAntiBot(Exception):
    """Il portale ha bloccato la richiesta (captcha / 403 / 429)."""


class ErroreHTTP(Exception):
    """Errore di rete non risolvibile dopo i tentativi previsti."""


@dataclass
class Limitatore:
    """Mantiene almeno `intervallo` secondi tra due richieste allo stesso host."""

    intervallo: float = 1.5
    _ultimo: dict[str, float] = field(default_factory=dict)

    def attendi(self, url: str) -> None:
        host = urlsplit(url).netloc or url
        ora = time.monotonic()
        precedente = self._ultimo.get(host)
        attesa = self.intervallo - (ora - precedente) if precedente else 0.0
        if attesa > 0:
            time.sleep(attesa)
        self._ultimo[host] = time.monotonic()


def crea_sessione(cfg: Config) -> requests.Session:
    sessione = requests.Session()
    sessione.headers.update({
        "User-Agent": cfg.user_agent,
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    return sessione


def _pagina_bloccata(html: str) -> bool:
    testo = html[:20_000].lower()
    return any(segnale in testo for segnale in SEGNALI_ANTIBOT)


def scarica(
    sessione: requests.Session,
    url: str,
    cfg: Config,
    limitatore: Limitatore | None = None,
) -> str:
    """Scarica una pagina con retry. Solleva ErroreAntiBot / ErroreHTTP."""
    ultimo_problema = ""

    for tentativo in range(1, cfg.tentativi + 1):
        if limitatore:
            limitatore.attendi(url)
        try:
            risposta = sessione.get(url, timeout=cfg.timeout)
        except requests.RequestException as exc:
            ultimo_problema = f"{type(exc).__name__}: {exc}"
        else:
            if risposta.status_code in (403, 429):
                attesa = _retry_after(risposta)
                if tentativo < cfg.tentativi and attesa is not None:
                    time.sleep(min(attesa, 30))  # esplicitamente richiesto dal sito
                    ultimo_problema = f"HTTP {risposta.status_code} (blocco temporaneo)"
                    continue
                raise ErroreAntiBot(
                    f"{urlsplit(url).netloc} ha bloccato la richiesta (HTTP "
                    f"{risposta.status_code})."
                )
            if risposta.status_code >= 500:
                ultimo_problema = f"HTTP {risposta.status_code}"
            elif risposta.status_code >= 400:
                raise ErroreHTTP(f"{url} -> HTTP {risposta.status_code}")
            else:
                html = risposta.text
                if _pagina_bloccata(html):
                    raise ErroreAntiBot(
                        f"{urlsplit(url).netloc} ha risposto con una pagina di verifica "
                        f"anti-bot invece dei risultati."
                    )
                return html

        if tentativo < cfg.tentativi:
            time.sleep(min(cfg.backoff * 2 ** (tentativo - 1), 8))

    raise ErroreHTTP(f"{url} non raggiungibile dopo {cfg.tentativi} tentativi "
                     f"({ultimo_problema})")


def _retry_after(risposta: requests.Response) -> float | None:
    valore = risposta.headers.get("Retry-After")
    if not valore:
        return None
    try:
        return float(valore)
    except ValueError:
        return None
