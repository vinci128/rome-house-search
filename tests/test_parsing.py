"""Test dell'estrazione dei dati dalle schede.

I casi marcati REGRESSIONE coprono bug della versione a file singolo.
"""

import pytest

from romasearch.parsing import (
    analizza_condizione,
    estrai_dalla_scheda,
    estrai_locali,
    estrai_mq,
    estrai_piano,
    estrai_prezzo,
    normalizza,
)


@pytest.mark.parametrize("testo, atteso", [
    ("€ 335.000", 335_000),
    ("335.000 €", 335_000),
    ("350000", 350_000),
    ("Prezzo: € 289.000", 289_000),
    ("prezzo 450.000 euro", 450_000),
    ("Vendita € 395.000", 395_000),
    ("su richiesta", None),
    ("Prezzo su richiesta", None),
    # REGRESSIONE: il prezzo al mq non deve diventare il prezzo di acquisto
    ("90 mq 350.000 € 3.888 €/mq", 350_000),
    ("90 mq, 1.200 €/mq", None),
    ("90 mq a 350 €/mq", None),
])
def test_estrai_prezzo(testo, atteso):
    assert estrai_prezzo(testo) == atteso


@pytest.mark.parametrize("testo, atteso", [
    ("3 locali", 3),
    ("locali 4", 4),
    ("4 vani", 4),
    ("vani: 5", 5),
    ("Trilocale", 3),
    ("QUADRILOCALE ristrutturato", 4),
    ("bilocale", 2),
    ("ottilocale con terrazzo", 8),
    ("6+ locali", 6),
    ("appartamento con posto auto", None),
    ("90 mq", None),
])
def test_estrai_locali(testo, atteso):
    assert estrai_locali(testo) == atteso


@pytest.mark.parametrize("testo, atteso", [
    ("90 mq", 90),
    ("superficie 120 m²", 120),
    ("95mq", 95),
    ("70 metri quadri", 70),
    ("350.000 € 3.500 €/mq", None),
    ("120 mq 3.000 €/mq", 120),
    ("Prezzo su richiesta", None),
])
def test_estrai_mq(testo, atteso):
    assert estrai_mq(testo) == atteso


@pytest.mark.parametrize("testo, atteso", [
    ("4° piano", "4"),
    ("piano 3", "3"),
    ("3 piano con ascensore", "3"),
    ("piano terra", "terra"),
    ("rialzato", "rialzato"),
    ("piano rialzato", "rialzato"),
    ("seminterrato", "seminterrato"),
    ("ultimo piano con terrazzo", "ultimo"),
    ("piano 5 di 6", "5"),
    ("nessun dato", None),
])
def test_estrai_piano(testo, atteso):
    assert estrai_piano(testo) == atteso


@pytest.mark.parametrize("testo, atteso", [
    ("da ristrutturare", "ristrutturare"),
    ("appartamento DA RISTRUTTURARE", "ristrutturare"),
    ("da rinnovare", "ristrutturare"),
    ("necessita lavori", "ristrutturare"),
    ("impianti da rifare", "ristrutturare"),
    ("non ristrutturato", "ristrutturare"),
    ("manutenzione straordinaria", "ristrutturare"),
    # REGRESSIONE: contiene "ristrutturato", ma non è un immobile pronto
    ("parzialmente ristrutturato", "parziale"),
    ("semi-ristrutturato", "parziale"),
    ("ristrutturato in parte", "parziale"),
    ("ristrutturato", "ottimo"),
    ("appena ristrutturato nel 2022", "ottimo"),
    ("nuova costruzione", "ottimo"),
    ("ottimo stato", "ottimo"),
    ("in ottime condizioni", "ottimo"),
    ("chiavi in mano", "ottimo"),
    ("poco usato", "ottimo"),
    # REGRESSIONE: parole troppo generiche, presenti in quasi tutte le schede
    ("appartamento luminoso con arredato di pregio", "unknown"),
    ("luminoso, ottima esposizione, lavori di manutenzione eseguiti", "unknown"),
    ("recente e moderno, ottimo locale", "unknown"),
])
def test_analizza_condizione(testo, atteso):
    condizione, _segnali = analizza_condizione(testo)
    assert condizione == atteso


def test_condizione_ritorna_i_segnali():
    condizione, segnali = analizza_condizione("appartamento da ristrutturare")
    assert condizione == "ristrutturare"
    assert segnali  # i segnali rendono la classificazione ispezionabile


def test_segno_negativo_vince_su_segno_positivo():
    # Testo contraddittorio: si sceglie il caso peggiore.
    assert analizza_condizione("ristrutturato nel 2010, ma da ristrutturare")[0] == "ristrutturare"


def test_normalizza_tolera_accenti_e_maiuscole():
    assert normalizza("  PIÙ  Bella\nCittà ") == "piu bella citta"


def test_estrai_dalla_scheda_completa():
    dati = estrai_dalla_scheda(
        "Quadrilocale in vendita · Torrino · 4 locali · 95 mq · 3° piano · "
        "€ 335.000 · da ristrutturare"
    )
    assert dati["prezzo"] == 335_000
    assert dati["locali"] == 4
    assert dati["mq"] == 95
    assert dati["piano"] == "3"
    assert dati["condizione"] == "ristrutturare"
    # I segnali sono esposti per poter controllare perché è stata scelta la classe.
    assert dati["segnali_condizione"]


def test_scheda_vuota_non_fa_fallire():
    dati = estrai_dalla_scheda("")
    assert dati["prezzo"] is None
    assert dati["condizione"] == "unknown"
