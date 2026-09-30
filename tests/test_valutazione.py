"""Test della valutazione economica: costi, filtri, deduplica, ranking."""

from romasearch.config import Config
from romasearch.models import Annuncio
from romasearch.valutazione import (
    riepilogo_scarti,
    seleziona,
    valuta,
    valuta_tutti,
)


def annuncio(**kwargs) -> Annuncio:
    dati = {"titolo": "Trilocale", "prezzo": 300_000, "fonte": "immobiliare.it"}
    dati.update(kwargs)
    return Annuncio(**dati)


# ─── Soldi ──────────────────────────────────────────────────────────────────────


def test_costo_totale_somma_i_lavori():
    v = valuta(annuncio(prezzo=300_000, mq=100, condizione="ristrutturare"), Config())
    assert v.costo_ristrutturazione == 70_000
    assert v.costo_totale == 370_000


def test_il_totale_e_sempre_coerente_col_prezzo():
    for condizione in ("ottimo", "parziale", "ristrutturare", "unknown"):
        v = valuta(annuncio(prezzo=250_000, mq=80, condizione=condizione), Config())
        assert v.costo_totale == v.prezzo + v.costo_ristrutturazione


def test_pronta_scheda_diplomatica():
    v = valuta(annuncio(mq=90, locali=3, condizione="ottimo"), Config())
    assert v.costo_ristrutturazione == 0
    assert not any("Ristrutturazione" in nota for nota in v.note)


def test_manutenzione_sconosciuta_viene_segnalata():
    v = valuta(annuncio(mq=90, locali=3), Config())
    assert v.costo_ristrutturazione == 0
    assert any("non dichiara" in nota for nota in v.note)


def test_prezzo_oltre_budget_ma_sotto_tetto_restano_accettato():
    cfg = Config(budget=350_000, margine_trattativa=0.12)
    v = valuta(annuncio(prezzo=380_000, mq=90, locali=3, condizione="ottimo"), cfg)
    assert v.ammissibile
    assert any("trattativa" in nota for nota in v.note)


# ─── Filtri ─────────────────────────────────────────────────────────────────────


def test_scarta_locali_insufficienti_con_motivo():
    cfg = Config(locali_minimi=3)
    valutazioni = valuta_tutti([annuncio(locali=2, mq=90)], cfg)
    assert seleziona(valutazioni, cfg) == []
    assert any("locali" in motivo for motivo in valutazioni[0].motivi_esclusione)
    assert sum(riepilogo_scarti(valutazioni).values()) == 1


def test_locali_sconosciuti_non_vengono_scartati():
    cfg = Config(locali_minimi=3)
    v = valuta(annuncio(locali=None, mq=90), cfg)
    assert v.ammissibile
    assert any("Locali non dichiarati" in nota for nota in v.note)


def test_scarta_oltre_il_tetto_di_ricerca():
    cfg = Config(budget=350_000)
    valutazioni = valuta_tutti([annuncio(prezzo=500_000, mq=90, locali=3)], cfg)
    assert seleziona(valutazioni, cfg) == []
    assert any("oltre il tetto" in motivo for motivo in valutazioni[0].motivi_esclusione)


def test_scarta_se_i_lavori_fanno_sforare_il_budget():
    cfg = Config(budget=350_000)
    # 320k + 100 mq × 700 €/mq = 390k: rientra nel tetto di 392k.
    v = valuta(annuncio(prezzo=320_000, mq=100, locali=3, condizione="ristrutturare"), cfg)
    assert v.costo_totale == 390_000
    assert v.ammissibile

    # Con ristrutturazione completa: 320k + 110k = 430k, escluso con motivazione.
    cfg_completa = Config(budget=350_000, livello_per_caso_peggiore="completa")
    valutazioni = valuta_tutti(
        [annuncio(prezzo=320_000, mq=100, locali=3, condizione="ristrutturare")], cfg_completa)
    assert seleziona(valutazioni, cfg_completa) == []
    assert any("costo complessivo" in motivo
               for motivo in valutazioni[0].motivi_esclusione)


def test_mq_minimo():
    cfg = Config(mq_minimi=80)
    assert seleziona([valuta(annuncio(mq=60, locali=3), cfg)], cfg) == []
    assert len(seleziona([valuta(annuncio(mq=90, locali=3), cfg)], cfg)) == 1


def test_richiedi_condizione_scarta_gli_ignoti():
    cfg = Config(richiedi_condizione=True)
    v = valuta(annuncio(mq=90, locali=3), cfg)
    assert not v.ammissibile
    assert v.motivi_esclusione == ["manutenzione non dichiarata"]


def test_seleziona_e_idempotente():
    cfg = Config()
    valutazioni = valuta_tutti([annuncio(locali=2, mq=90)], cfg)
    seleziona(valutazioni, cfg)
    assert len(valutazioni[0].motivi_esclusione) == 1


# ─── Deduplica ──────────────────────────────────────────────────────────────────


def test_dedup_per_url():
    cfg = Config()
    duplicati = [
        annuncio(url="https://www.immobiliare.it/annunci/1/", locali=3, mq=90),
        annuncio(url="https://immobiliare.it/annunci/1/?utm_source=news", locali=3, mq=90),
    ]
    assert len(valuta_tutti(duplicati, cfg)) == 1


def test_stesso_url_ma_siti_diversi_restano_separati():
    cfg = Config()
    a = annuncio(url="https://www.immobiliare.it/annunci/1/", fonte="immobiliare.it")
    b = annuncio(url="https://www.immobiliare.it/annunci/1/", fonte="subito.it")
    assert len(valuta_tutti([a, b], cfg)) == 2


def test_dedup_tiene_la_scheda_piu_completa():
    cfg = Config()
    povero = annuncio(url="https://x.it/1", prezzo=300_000)
    ricco = annuncio(url="https://x.it/1", prezzo=300_000, locali=3, mq=90, piano="3")
    unici = valuta_tutti([povero, ricco], cfg)
    assert len(unici) == 1
    assert unici[0].annuncio.mq == 90


# ─── Ranking ────────────────────────────────────────────────────────────────────


def test_ordina_per_punteggio_decrescente():
    cfg = Config()
    economico = annuncio(titolo="A", prezzo=250_000, locali=3, mq=80, condizione="ottimo")
    caro = annuncio(titolo="B", prezzo=390_000, locali=4, mq=140, condizione="ottimo")
    ordinati = seleziona(valuta_tutti([caro, economico], cfg), cfg)
    assert [v.annuncio.titolo for v in ordinati] == ["A", "B"]
    assert ordinati[0].punteggio > ordinati[1].punteggio


def test_il_case_peggiore_penalizza_il_punteggio():
    cfg = Config()
    pronto = annuncio(prezzo=300_000, locali=3, mq=90, condizione="ottimo")
    da_fare = annuncio(prezzo=300_000, locali=3, mq=90, condizione="ristrutturare")
    ordinati = seleziona(valuta_tutti([pronto, da_fare], cfg), cfg)
    assert ordinati[0].annuncio.condizione == "ottimo"


def test_punteggio_sempre_nel_range():
    cfg = Config(budget=100_000, margine_trattativa=1.0)
    assurdo = annuncio(prezzo=999_000, mq=15, locali=9, condizione="ristrutturare")
    for v in seleziona([valuta(assurdo, cfg)], cfg):
        assert 0 <= v.punteggio <= 100


def test_il_punteggio_e_spiegato():
    cfg = Config()
    v = seleziona(valuta_tutti([annuncio(prezzo=300_000, locali=3, mq=90)], cfg), cfg)[0]
    assert v.motivi_punteggio
    assert any("margine di budget" in motivo for motivo in v.motivi_punteggio)


def test_to_dict_contiene_il_verdetto():
    cfg = Config()
    v = seleziona(valuta_tutti([annuncio(prezzo=300_000, locali=3, mq=90)], cfg), cfg)[0]
    dati = v.to_dict()
    assert dati["ammissibile"] is True
    assert dati["costo_totale"] == 300_000
    assert dati["punteggio"] > 0
