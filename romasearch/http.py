"""Accesso HTTP educato ai portali: sessione, retry con backoff, rate limit.

I portali immobiliari hanno protezioni anti-bot. Non le aggiriamo: se una
richiesta viene bloccata lo diciamo chiaramente e continuiamo con gli altri
siti, invece di spacciare uno zero risultati per una ricerca senza esito.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from .config import Config

if TYPE_CHECKING:
    import requests

# Importata qui per non obbligare chi usa solo --links ad avere requests
# installato: la sessione serve solo per il download effettivo.
_ERRORI_REQUESTS = {
    "ConnectionError", "ConnectTimeout", "HTTPError", "ReadTimeout",
    "Timeout", "TooManyRedirects", "InvalidURL", "ChunkedEncodingError",
    "ProxyError", "SSLError", "RequestException",
}

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
    import requests  # noqa: PLC0415 - caricato qui, vedi nota in fondo al modulo

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


def _prova_una(
    sessione: requests.Session,
    url: str,
    cfg: Config,
    tentativo: int,
) -> tuple[str | None, str]:
    """Un tentativo di download.

    Restituisce (html, motivo_del_rinvio): l'HTML se la pagina va bene, altrimenti
    None e la causa, da riportare se tutti i tentativi falliscono. Solleva
    ErroreAntiBot / ErroreHTTP quando riprovare non serve.
    """
    risposta = sessione.get(url, timeout=cfg.timeout)

    if risposta.status_code in (403, 429):
        attesa = _retry_after(risposta)
        if tentativo < cfg.tentativi and attesa is not None:
            # Il sito ha chiesto esplicitamente di aspettare: si ascolta.
            time.sleep(min(attesa, 30))
            return None, f"HTTP {risposta.status_code} (blocco temporaneo)"
        raise ErroreAntiBot(
            f"{urlsplit(url).netloc} ha bloccato la richiesta (HTTP {risposta.status_code})."
        )
    if risposta.status_code >= 500:
        return None, f"HTTP {risposta.status_code}"  # errore del sito: si riprova
    if risposta.status_code >= 400:
        raise ErroreHTTP(f"{url} -> HTTP {risposta.status_code}")

    html = risposta.text
    if _pagina_bloccata(html):
        raise ErroreAntiBot(
            f"{urlsplit(url).netloc} ha risposto con una pagina di verifica "
            f"anti-bot invece dei risultati."
        )
    return html, ""


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
            html, motivo = _prova_una(sessione, url, cfg, tentativo)
        except Exception as exc:  # noqa: BLE001 - solo gli errori di rete si riprovano
            if type(exc).__name__ not in _ERRORI_REQUESTS:
                raise
            html, motivo = None, f"{type(exc).__name__}: {exc}"
        if html is not None:
            return html
        ultimo_problema = motivo

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


# Nota: `requests` è importato dentro le funzioni che lo usano, non a livello
# di modulo, così `--links` (che costruisce solo URL, senza rete) funziona anche
# se le dipendenze non sono installate. Gli errori di rete sono riconosciuti per
# nome di classe: è l'unico modo per trattarli senza importare requests qui.
