"""Test di configurazione: budget, tetto di ricerca, costi."""

import pytest

from romasearch.config import ZONE, Config, CostiRistrutturazione, get_zona


def test_predefiniti():
    cfg = Config()
    assert cfg.budget == 350_000
    assert cfg.locali_minimi == 3
    assert cfg.prezzo_max_ricerca == 392_000  # 350k + 12% di trattativa
    assert cfg.zone == ("torrino",)


def test_prezzo_max_da_ristrutturare_deriva_dai_costi():
    # 350.000 - (75 mq × 700 €/mq) = 297.500: niente più numeri magici.
    assert Config().prezzo_max_da_ristrutturare == 297_500
    # REGRESSIONE: i link di ricerca usavano 270.000 scritto a mano.
    assert Config().prezzo_max_da_ristrutturare != 270_000


def test_prezzo_max_da_ristrutturare_segue_livello():
    completa = Config(livello_per_caso_peggiore="completa")
    assert completa.prezzo_max_da_ristrutturare == 350_000 - 75 * 1100


def test_query_locali():
    assert Config(locali_minimi=3).query_locali == "3,4,5,6,7,8,9,10"
    assert Config(locali_minimi=2).query_locali == "2,3,4,5,6,7,8,9,10"


@pytest.mark.parametrize("condizione, atteso", [
    ("ottimo", 0),
    ("unknown", 0),
    ("parziale", 75 * 350),
    ("ristrutturare", 75 * 700),
])
def test_costo_ristrutturazione(condizione, atteso):
    assert Config().costo_ristrutturazione(None, condizione) == atteso


def test_costo_ristrutturazione_usa_i_mq_dichiarati():
    assert Config().costo_ristrutturazione(120, "ristrutturare") == 120 * 700


def test_costo_ristrutturazione_rispetta_i_costi_personalizzati():
    cfg = Config(costi=CostiRistrutturazione(leggera=400, media=800, completa=1200))
    assert cfg.costo_ristrutturazione(100, "ristrutturare") == 80_000
    assert cfg.costo_ristrutturazione(100, "parziale") == 40_000


def test_mq_di_riferimento_configurabile():
    cfg = Config(costi=CostiRistrutturazione(mq_di_riferimento=100))
    assert cfg.costo_ristrutturazione(None, "ristrutturare") == 100 * 700


def test_con_crea_una_copia():
    cfg = Config()
    assert cfg.con(budget=250_000).budget == 250_000
    assert cfg.budget == 350_000


@pytest.mark.parametrize("kwargs", [
    {"budget": 0},
    {"budget": -1},
    {"locali_minimi": 0},
    {"zone": ("quartiere-inesistente",)},
    {"livello_per_caso_peggiore": "enorme"},
])
def test_configurazioni_invalide(kwargs):
    with pytest.raises(ValueError):
        Config(**kwargs)


def test_zona_inesistente_mostra_i_nomi_validi():
    with pytest.raises(KeyError) as errore:
        get_zona("eur-torino")
    assert "torrino" in str(errore.value)


def test_tutte_le_zone_hanno_i_dati_per_i_portali():
    for nome, zona in ZONE.items():
        assert zona.slug_immobiliare.endswith("-roma"), nome
        assert zona.slug_idealista, nome
        assert zona.ricerca_casa, nome
        assert zona.indirizzo_fallback.startswith("Roma"), nome
