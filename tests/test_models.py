"""Test del modello annuncio: €/mq, URL normalizzato, chiave di deduplica."""

from romasearch.models import Annuncio


def annuncio(**kwargs) -> Annuncio:
    dati = {"titolo": "Trilocale", "prezzo": 300_000, "fonte": "immobiliare.it"}
    dati.update(kwargs)
    return Annuncio(**dati)


def test_prezzo_al_mq():
    assert annuncio(prezzo=300_000, mq=100).prezzo_al_mq == 3_000
    assert annuncio(prezzo=300_000).prezzo_al_mq is None


def test_etichetta_condizione():
    assert annuncio(condizione="ottimo").etichetta_condizione == "Pronto / ristrutturato"
    assert annuncio(condizione="unknown").etichetta_condizione == "Da verificare"


def test_url_normalizzata_rimuove_il_rumore():
    a = annuncio(url="https://www.immobiliare.it/annunci/123/?utm_source=x&pag=2#top")
    assert a.url_normalizzata == "https://immobiliare.it/annunci/123"


def test_url_normalizzata_conserva_i_filtri():
    a = annuncio(url="https://www.immobiliare.it/annunci/123/?locali=3")
    assert a.url_normalizzata == "https://immobiliare.it/annunci/123?locali=3"


def test_url_assolute_rimaste_quelle():
    assert annuncio(url="https://immobiliare.it/annunci/123").chiave().startswith("url:")


def test_chiave_di_fallback_senza_url():
    a = annuncio(titolo="Trilocale in Via D'Iliria", prezzo=300_000, mq=90)
    b = annuncio(titolo="trilocale  in via d'iliria ", prezzo=300_000, mq=90)
    assert a.chiave() == b.chiave()


def test_chiavi_diverse_per_annunci_diversi():
    assert annuncio(prezzo=300_000).chiave() != annuncio(prezzo=310_000).chiave()


def test_to_dict_contiene_il_prezzo_al_mq():
    dati = annuncio(mq=100).to_dict()
    assert dati["prezzo_al_mq"] == 3_000
    assert dati["fonte"] == "immobiliare.it"
    assert "costo_totale" not in dati  # i soldi stanno nella valutazione


def test_url_vuota_non_fa_fallire():
    assert annuncio().url_normalizzata == ""
    assert annuncio().chiave().startswith("cont:")
