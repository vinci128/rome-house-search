"""Test dei selettori e della costruzione degli URL, su HTML di esempio."""

import pytest

from romasearch.config import Config, get_zona
from romasearch.scrapers import casa, idealista, immobiliare, link_ricerca, raccogli
from romasearch.scrapers.base import (
    ProfiloSito,
    estrai_annunci,
    scarica_e_estrai,
)
from romasearch.scrapers.base import (
    link_ricerca as link_ricerca_del_sito,
)

CFG = Config()
ZONA = get_zona("torrino")

HTML_IMMOBILIARE = """
<ul class="nd-list">
  <li class="nd-list__item">
    <a class="in-listingCard__title" href="/annunci/498211234/">
      <h2 class="nd-listing-card__title">Quadrilocale ristrutturato in vendita</h2>
    </a>
    <div class="nd-listing-card__price">€ 335.000</div>
    <p class="nd-listing-card__location">Via Sandro Botticelli, Torrino</p>
    <ul class="in-listingCard__features">
      <li>4 locali</li><li>95 mq</li><li>3° piano</li>
    </ul>
  </li>
  <li class="nd-list__item">
    <a class="in-listingCard__title" href="/annunci/498211999/">
      <h2 class="nd-listing-card__title">Appartamento da ristrutturare</h2>
    </a>
    <div class="nd-listing-card__price">€ 289.000</div>
    <p class="nd-listing-card__location">Via Igino Giordani, Torrino</p>
    <ul class="in-listingCard__features">
      <li>3 locali</li><li>110 mq</li><li>1° piano</li>
    </ul>
  </li>
  <li class="nd-list__item">
    <a class="in-listingCard__title" href="/annunci/498211999/?utm_source=listino">
      <h2 class="nd-listing-card__title">Appartamento da ristrutturare</h2>
    </a>
    <div class="nd-listing-card__price">€ 289.000</div>
    <ul class="in-listingCard__features"><li>3 locali</li><li>110 mq</li></ul>
  </li>
  <li class="nd-list__item">
    <span>Pubblicità premium senza prezzo</span>
  </li>
</ul>
"""

HTML_IDEALISTA = """
<article class="item" data-adid="123456">
  <a class="item-link" href="/immobile/98765432/">
    <span class="item-detail-h1">Bilocale luminoso ad EUR</span>
  </a>
  <div class="item-detail-price">€ 210.000</div>
  <div class="item-detail-location">Torrino, Roma</div>
  <p class="item-detail">2 locali · 60 mq · 2ª piano</p>
</article>
"""

HTML_CASA = """
<article class="listing-card">
  <a href="/immobile/roma/torrino/vendita/AA12345.shtml">
    <h2 class="listing-card__title">Villa da ristrutturare con giardino</h2>
  </a>
  <span class="listing-card__price">€ 340.000</span>
  <div class="listing-card__address">Via Lilio Alberto Silla, Torrino</div>
  <p>5 locali · 180 mq · piano terra</p>
</article>
"""

SCHEDA_PULITA = "<html><body><p>Nessun risultato</p></body></html>"


# ─── Selettori ──────────────────────────────────────────────────────────────────


def test_immobiliare_estrae_tutti_i_campi():
    annunci = estrai_annunci(HTML_IMMOBILIARE, immobiliare.PROFILO, ZONA)
    primo = annunci[0]
    assert primo.titolo == "Quadrilocale ristrutturato in vendita"
    assert primo.prezzo == 335_000
    assert primo.locali == 4
    assert primo.mq == 95
    assert primo.piano == "3"
    assert primo.condizione == "ottimo"
    assert primo.url == "https://www.immobiliare.it/annunci/498211234/"
    assert primo.fonte == "immobiliare.it"
    assert primo.zona == "torrino"
    assert "Botticelli" in primo.indirizzo


def test_immobiliare_deduplica_dentro_la_pagina():
    annunci = estrai_annunci(HTML_IMMOBILIARE, immobiliare.PROFILO, ZONA)
    # Quattro <li>, ma uno è duplicato e uno non ha prezzo.
    assert len(annunci) == 2


def test_immobiliare_classifica_il_da_ristrutturare():
    annunci = estrai_annunci(HTML_IMMOBILIARE, immobiliare.PROFILO, ZONA)
    secondo = annunci[1]
    # REGRESSIONE: prima finiva tra i "pronti" perché conteneva "ristrutturato".
    assert secondo.condizione == "ristrutturare"
    assert Config().costo_ristrutturazione(secondo.mq, secondo.condizione) == 110 * 700


def test_idealista():
    annunci = estrai_annunci(HTML_IDEALISTA, idealista.PROFILO, ZONA)
    assert len(annunci) == 1
    a = annunci[0]
    assert a.prezzo == 210_000
    assert a.locali == 2
    assert a.mq == 60
    assert a.url == "https://www.idealista.it/immobile/98765432/"


def test_casa_it():
    annunci = estrai_annunci(HTML_CASA, casa.PROFILO, ZONA)
    a = annunci[0]
    assert a.prezzo == 340_000
    assert a.locali == 5
    assert a.mq == 180
    assert a.piano == "terra"
    assert a.condizione == "ristrutturare"


@pytest.mark.parametrize("modulo", [immobiliare, idealista, casa])
def test_pagina_vuota_non_pha_fallire(modulo):
    assert estrai_annunci(SCHEDA_PULITA, modulo.PROFILO, ZONA) == []


def test_html_malformato_non_pha_fallire():
    assert estrai_annunci("<<< non è html", immobiliare.PROFILO, ZONA) == []


# ─── Raccolta con problemi ──────────────────────────────────────────────────────


class RispostaFinta:
    def __init__(self, testo="", status=200, headers=None):
        self.text = testo
        self.status_code = status
        self.headers = headers or {}


class SessioneFinta:
    def __init__(self, risposte):
        self.risposte = risposte
        self.chiamate = []

    def get(self, url, timeout=None):
        self.chiamate.append(url)
        return self.risposte.get(url, RispostaFinta(SCHEDA_PULITA))


def test_scarica_e_estrai_segnala_le_pagine_senza_schede():
    sessione = SessioneFinta({})
    annunci, problemi = scarica_e_estrai(
        sessione, ["https://www.immobiliare.it/x"], immobiliare.PROFILO, ZONA, CFG)
    assert annunci == []
    assert len(problemi) == 1
    assert "selettori" in problemi[0]


def test_un_sito_che_fallisce_non_ferma_gli_altri():
    sessione = SessioneFinta({"https://www.immobiliare.it/x": RispostaFinta(HTML_IMMOBILIARE)})
    annunci, problemi = scarica_e_estrai(
        sessione,
        ["https://www.immobiliare.it/x", "https://www.idealista.it/y"],
        immobiliare.PROFILO, ZONA, CFG,
    )
    assert len(annunci) == 2
    assert len(problemi) == 1


def test_il_profilo_ha_il_sito_e_il_dominio():
    for modulo in (immobiliare, idealista, casa):
        assert isinstance(modulo.PROFILO, ProfiloSito)
        assert modulo.PROFILO.sito == modulo.SITO
        assert modulo.PROFILO.dominio == modulo.DOMINIO
        assert modulo.PROFILO.card


# ─── URL ────────────────────────────────────────────────────────────────────────


def test_url_immobiliare():
    url = immobiliare.url_ricerca(ZONA, CFG)
    assert url == ("https://www.immobiliare.it/vendita-case/torrino-roma/"
                   "?locali=3,4,5,6plus&prezzoMassimo=392000")
    assert immobiliare.url_ricerca(ZONA, CFG, pagina=2).endswith("&pag=2")


def test_url_immobiliare_da_ristrutturare():
    url = immobiliare.url_da_ristrutturare(ZONA, CFG)
    assert "prezzoMassimo=297500" in url
    assert "parole_chiave=da+ristrutturare" in url


def test_url_idealista():
    url = idealista.url_ricerca(ZONA, CFG)
    assert url == ("https://www.idealista.it/vendita-case/roma-rm/torrino/"
                   "?ordine=prezzo-asc&prezzoMax=392000&locali=3,4,5,6,7,8,9,10")


def test_url_casa_it():
    url = casa.url_ricerca(ZONA, CFG)
    assert url == ("https://www.casa.it/vendita/residenziale/roma/pag-1/"
                   "?locali_min=3&prezzo_max=392000&q=torrino")
    assert "pag-2" in casa.url_ricerca(ZONA, CFG, pagina=2)


def test_gli_url_rispettano_i_filtri():
    cfg = Config(locali_minimi=4, budget=250_000)
    for modulo in (immobiliare, idealista, casa):
        for url in link_ricerca_del_sito(modulo.url_ricerca, modulo.url_da_ristrutturare,
                                          ZONA, cfg):
            # Ogni link filtra per prezzo (tetto normale o tetto "da ristrutturare") e locali.
            assert (str(cfg.prezzo_max_ricerca) in url
                    or str(cfg.prezzo_max_da_ristrutturare) in url), url
            assert "4" in url


def test_il_budget_si_propaga_negli_url():
    cfg = Config(budget=200_000)
    for modulo in (immobiliare, idealista, casa):
        assert "224000" in modulo.url_ricerca(ZONA, cfg)  # 200k + 12%


def test_link_ricerca_copre_tutti_i_portali():
    links = link_ricerca(CFG)
    nomi = [nome for nome, _ in links]
    for sito in ("immobiliare.it", "idealista.it", "casa.it", "subito.it"):
        assert any(sito in nome for nome in nomi), sito
    assert all(url.startswith("https://") for _, url in links)


def test_link_ricerca_solo_da_ristrutturare():
    links = link_ricerca(Config(solo_ristrutturare=True))
    assert all("da+ristrutturare" in url or "da%20ristrutturare" in url
               for _, url in links)


def test_zona_multipla():
    cfg = Config(zone=("torrino", "eur"))
    links = link_ricerca(cfg)
    assert any("EUR" in nome for nome, _ in links)
    assert len({url for _, url in links}) == len(links)  # nessun link duplicato


def test_i_figli_della_card_non_vengono_letti_come_annunci():
    # "listing-card" aggancia anche il titolo e il prezzo: solo la card esterna
    # deve produrre un annuncio, altrimenti si perdono locali, mq e link.
    annunci = estrai_annunci(HTML_CASA, casa.PROFILO, ZONA)
    assert len(annunci) == 1
    assert annunci[0].locali == 5
    assert annunci[0].mq == 180
    assert annunci[0].url.endswith("AA12345.shtml")


def test_i_segnali_sono_leggibili():
    annunci = estrai_annunci(HTML_CASA, casa.PROFILO, ZONA)
    assert annunci[0].segnali_condizione == ["da ristrutturare"]


@pytest.mark.parametrize("modulo, host", [
    (immobiliare, "immobiliare.it"),
    (idealista, "idealista.it"),
    (casa, "casa.it"),
])
def test_scrape_per_portale(modulo, host):
    """Ogni portale deve riuscire a interrogare le proprie URL."""
    risposte = {
        "immobiliare.it": HTML_IMMOBILIARE,
        "idealista.it": HTML_IDEALISTA,
        "casa.it": HTML_CASA,
    }
    sessione = SessioneFinta({})  # qualunque URL: risponde con l'HTML del sito

    def get(url, timeout=None):
        sessione.chiamate.append(url)
        return RispostaFinta(risposte[host])

    sessione.get = get
    annunci, problemi = modulo.scrape(sessione, ZONA, CFG)

    assert annunci, "nessun annuncio estratto"
    assert problemi == []
    # Una ricerca normale più la variante "da ristrutturare".
    assert len(sessione.chiamate) == 2
    assert host in sessione.chiamate[0]


def test_scrape_con_solo_da_ristrutturare():
    sessione = SessioneFinta({})

    def get(url, timeout=None):
        sessione.chiamate.append(url)
        return RispostaFinta(HTML_IMMOBILIARE)

    sessione.get = get
    annunci, problemi = immobiliare.scrape(sessione, ZONA, Config(solo_ristrutturare=True))
    assert len(sessione.chiamate) == 1
    assert "parole_chiave=da+ristrutturare" in sessione.chiamate[0]
    assert annunci


def test_i_problemi_ripetuti_sono_raggruppati():
    """Lo stesso blocco su più pagine va segnalato una volta sola."""
    cfg = Config(pagine_per_zona=3, pausa=0)
    raccolta = raccogli(cfg, sessione=SessioneFinta({}))
    assert raccolta.annunci == []
    assert len(raccolta.problemi) == len(set(raccolta.problemi))
    assert len(raccolta.problemi) == 3  # uno per portale
