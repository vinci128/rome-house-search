"""Parsing generico delle schede: un solo corpo di codice per tutti i portali.

Ogni sito dichiara solo i suoi selettori CSS (`ProfiloSito`); la logica di
estrazione è condivisa. Aggiungere un portale significa aggiungere un modulo,
non copiare 80 righe.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from bs4 import BeautifulSoup, Tag

from ..config import Config, Zona
from ..formato import euro
from ..http import Limitatore, scarica
from ..models import Annuncio
from ..parsing import estrai_dalla_scheda

LIMITI_SCHEDE = 40
MAX_CARATTERI_TITOLO = 90


@dataclass(frozen=True)
class ProfiloSito:
    """Selettori CSS di un portale, provati in ordine fino al primo match."""

    sito: str
    dominio: str
    card: tuple[str, ...]
    titolo: tuple[str, ...] = ("[class*='title']", "h2", "h3", "a")
    prezzo: tuple[str, ...] = ("[class*='price']", "[class*='Price']")
    indirizzo: tuple[str, ...] = ("[class*='address']", "[class*='location']")
    url: tuple[str, ...] = ("a[href*='/annunci/']", "a[href]")
    card_max: int = LIMITI_SCHEDE


def _primo(nodo: Tag, selettori: Iterable[str]) -> Tag | None:
    for selettore in selettori:
        trovato = nodo.select_one(selettore)
        if trovato is not None:
            return trovato
    return None


def _testo(nodo: Tag | None) -> str:
    if nodo is None:
        return ""
    if isinstance(nodo, Tag):
        return nodo.get_text(" ", strip=True)
    return str(nodo).strip()


def _url_assoluto(href: str, dominio: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    if href.startswith("//"):
        return f"https:{href}"
    return f"https://{dominio}{href if href.startswith('/') else '/' + href}"


def link_ricerca(url_ricerca, url_da_ristrutturare, zona: Zona, config: Config) -> list[str]:
    """Gli URL da aprire a mano per un portale: ricerca + variante da ristrutturare."""
    pagine = range(1, config.pagine_per_zona + 1)
    if config.solo_ristrutturare:
        return [url_da_ristrutturare(zona, config, pagina) for pagina in pagine]

    urls = [url_ricerca(zona, config, pagina) for pagina in pagine]
    if config.pagine_per_zona == 1:
        urls.append(url_da_ristrutturare(zona, config))
    return urls


def _senza_annidate(cards: list[Tag]) -> list[Tag]:
    """Tiene solo le card "più esterne".

    Un selettore come ``[class*='listing-card']`` aggancia anche i figli della
    card (titolo, prezzo): senza questo filtro quei frammenti verrebbero letti
    come annunci a sé, perdendo metà dei dati.
    """
    esterne: list[Tag] = []
    for card in cards:
        antenati = {id(genitore) for genitore in card.parents}
        if any(id(altra) in antenati for altra in cards if altra is not card):
            continue
        esterne.append(card)
    return esterne


def estrai_annunci(html: str, profilo: ProfiloSito, zona: Zona) -> list[Annuncio]:
    """Estrae gli annunci da una pagina di risultati."""
    soup = BeautifulSoup(html, "lxml")

    cards: list[Tag] = []
    for selettore in profilo.card:
        cards = _senza_annidate(soup.select(selettore))
        if cards:
            break
    if not cards:
        return []

    annunci: list[Annuncio] = []
    visti: set[str] = set()
    for card in cards[: profilo.card_max]:
        annuncio = _annuncio_da_card(card, profilo, zona)
        if annuncio is None:
            continue
        chiave = annuncio.chiave()
        if chiave in visti:
            continue
        visti.add(chiave)
        annunci.append(annuncio)
    return annunci


def _annuncio_da_card(card: Tag, profilo: ProfiloSito, zona: Zona) -> Annuncio | None:
    testo_card = card.get_text(" ", strip=True)
    if not testo_card:
        return None

    dati = estrai_dalla_scheda(testo_card)

    nodo_prezzo = _primo(card, profilo.prezzo)
    prezzo = estrai_dalla_scheda(_testo(nodo_prezzo))["prezzo"] if nodo_prezzo else None
    if prezzo is None:
        prezzo = dati["prezzo"]
    if prezzo is None:
        return None

    titolo = _testo(_primo(card, profilo.titolo)) or f"Annuncio {euro(prezzo)}"
    link = _primo(card, profilo.url)

    return Annuncio(
        titolo=titolo[:MAX_CARATTERI_TITOLO],
        prezzo=prezzo,
        fonte=profilo.sito,
        url=_url_assoluto(link["href"], profilo.dominio) if link else "",
        indirizzo=_testo(_primo(card, profilo.indirizzo)) or zona.indirizzo_fallback,
        zona=zona.nome,
        locali=dati["locali"],
        mq=dati["mq"],
        piano=dati["piano"],
        condizione=dati["condizione"],
        segnali_condizione=dati["segnali_condizione"],
    )


def scarica_e_estrai(
    sessione,
    urls: list[str],
    profilo: ProfiloSito,
    zona: Zona,
    config: Config,
    *,
    limitatore: Limitatore | None = None,
) -> tuple[list[Annuncio], list[str]]:
    """Scarica ogni URL e raccoglie gli annunci. Ritorna (annunci, problemi)."""
    annunci: list[Annuncio] = []
    problemi: list[str] = []
    visti: set[str] = set()
    pagine_vuote = 0
    prima_url_vuota = ""

    for url in urls:
        try:
            html = scarica(sessione, url, config, limitatore)
        except Exception as exc:  # noqa: BLE001 - un sito non deve fermare gli altri
            problemi.append(f"{profilo.sito}: {exc}")
            continue

        trovati = estrai_annunci(html, profilo, zona)
        if not trovati:
            pagine_vuote += 1
            prima_url_vuota = prima_url_vuota or url
            continue

        for annuncio in trovati:
            chiave = annuncio.chiave()
            if chiave in visti:
                continue
            visti.add(chiave)
            annunci.append(annuncio)

    if pagine_vuote:
        plural = "pagine" if pagine_vuote > 1 else "pagina"
        problemi.append(
            f"{profilo.sito}: nessuna scheda riconosciuta in {pagine_vuote} {plural} "
            f"(prima: {prima_url_vuota}) — selettori da aggiornare o pagina vuota"
        )

    return annunci, problemi
