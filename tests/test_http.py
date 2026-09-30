"""Test dello strato HTTP: retry, anti-bot, rate limit."""

import time

import pytest
import requests

from romasearch.config import Config
from romasearch.http import ErroreAntiBot, ErroreHTTP, Limitatore, crea_sessione, scarica

# backoff=0: i test non devono aspettare i tempi di rientro.
CFG = Config(pausa=0, tentativi=3, timeout=1, backoff=0)


class Risposta:
    def __init__(self, testo="<html>ok</html>", status=200, headers=None):
        self.text = testo
        self.status_code = status
        self.headers = headers or {}


class Sessione:
    """Sessione finta: restituisce risposte in sequenza."""

    def __init__(self, risposte):
        self.risposte = list(risposte)
        self.chiamate = 0

    def get(self, url, timeout=None):
        self.chiamate += 1
        prossima = self.risposte.pop(0)
        if isinstance(prossima, Exception):
            raise prossima
        return prossima


def test_ritorna_il_contenuto():
    assert scarica(Sessione([Risposta()]), "https://x.it", CFG) == "<html>ok</html>"


def test_riprova_su_errore_del_server():
    sessione = Sessione([Risposta(status=503), Risposta(status=500), Risposta()])
    assert scarica(sessione, "https://x.it", CFG) == "<html>ok</html>"
    assert sessione.chiamate == 3


def test_renuncia_alle_fine_dei_giorni():
    sessione = Sessione([Risposta(status=500)] * 5)
    with pytest.raises(ErroreHTTP) as errore:
        scarica(sessione, "https://x.it", CFG)
    assert sessione.chiamate == CFG.tentativi
    assert "non raggiungibile" in str(errore.value)


def test_riprova_su_eccezione_di_rete():
    sessione = Sessione([requests.ConnectionError("boom"), Risposta()])
    assert scarica(sessione, "https://x.it", CFG) == "<html>ok</html>"
    assert sessione.chiamate == 2


def test_403_e_un_blocco_non_riprova():
    sessione = Sessione([Risposta(status=403)])
    with pytest.raises(ErroreAntiBot) as errore:
        scarica(sessione, "https://immobiliare.it/x", CFG)
    assert sessione.chiamate == 1
    assert "bloccato" in str(errore.value)


def test_429_rispetta_retry_after():
    sessione = Sessione([
        Risposta(status=429, headers={"Retry-After": "0"}),
        Risposta(),
    ])
    assert scarica(sessione, "https://x.it", CFG) == "<html>ok</html>"
    assert sessione.chiamate == 2


def test_404_non_e_riprova():
    sessione = Sessione([Risposta(status=404)] * 3)
    with pytest.raises(ErroreHTTP):
        scarica(sessione, "https://x.it", CFG)
    assert sessione.chiamate == 1


@pytest.mark.parametrize("pagina", [
    "<html><body>Verifica che sei un umano</body></html>",
    "<html><body>Ray ID: 8f3a</body></html>",
    "<html><body>Please enable JavaScript and cookies to continue</body></html>",
])
def test_pagine_anti_bot(pagina):
    with pytest.raises(ErroreAntiBot) as errore:
        scarica(Sessione([Risposta(pagina)]), "https://casa.it/x", CFG)
    assert "anti-bot" in str(errore.value)


def test_pagina_legittima_non_falsa_positivo():
    pagina = "<html><body><h1>Appartamento con cucina attrezzata</h1></body></html>"
    assert scarica(Sessione([Risposta(pagina)]), "https://x.it", CFG) == pagina


def test_sessione_con_header():
    sessione = crea_sessione(Config())
    assert "rome-house-search" not in sessione.headers["User-Agent"]
    assert sessione.headers["Accept-Language"].startswith("it-IT")


def test_limitatore_rispetta_la_pausa():
    limitatore = Limitatore(intervallo=0.05)
    limitatore.attendi("https://a.it/1")
    inizio = time.monotonic()
    limitatore.attendi("https://a.it/2")
    assert time.monotonic() - inizio >= 0.04

    # Un altro host non aspetta.
    inizio = time.monotonic()
    limitatore.attendi("https://b.it/1")
    assert time.monotonic() - inizio < 0.04
