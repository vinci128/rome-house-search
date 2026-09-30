"""Valutazione economica e ranking degli annunci.

Un annuncio "compatibile" non viene più scartato in silenzio: ogni scarto ha
un motivo registrato (`motivi_esclusione`), così il risultato è verificabile e
l'utente sa cosa sta perdendo.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

from .config import Config
from .formato import euro, migliaia
from .models import Annuncio

PESO_BUDGET = 30.0
PESO_EURO_MQ = 25.0
PESO_SUPERFICIE = 15.0
PESO_CONDIZIONE = 12.0
PESO_COMPLETEZZA = 8.0

PUNTEGGIO_CONDIZIONE = {
    "ottimo": 1.0,
    "parziale": 0.5,
    "ristrutturare": 0.0,
    "unknown": 0.25,
}


@dataclass
class Valutazione:
    """Annuncio + i soldi + il verdetto."""

    annuncio: Annuncio
    costo_ristrutturazione: int
    costo_totale: int
    punteggio: float = 0.0
    motivi_punteggio: list[str] = field(default_factory=list)
    note: list[str] = field(default_factory=list)
    motivi_esclusione: list[str] = field(default_factory=list)

    @property
    def prezzo(self) -> int:
        return self.annuncio.prezzo

    @property
    def prezzo_al_mq(self) -> int | None:
        return self.annuncio.prezzo_al_mq

    @property
    def ammissibile(self) -> bool:
        return not self.motivi_esclusione

    def chiave(self) -> str:
        return self.annuncio.chiave()

    def to_dict(self) -> dict:
        return {
            **self.annuncio.to_dict(),
            "costo_ristrutturazione": self.costo_ristrutturazione,
            "costo_totale": self.costo_totale,
            "punteggio": round(self.punteggio, 1),
            "motivi_punteggio": list(self.motivi_punteggio),
            "note": list(self.note),
            "ammissibile": self.ammissibile,
            "motivi_esclusione": list(self.motivi_esclusione),
        }


# ─── Primo passaggio: i soldi ───────────────────────────────────────────────────


def valuta(annuncio: Annuncio, cfg: Config) -> Valutazione:
    """Calcola costi e note di un singolo annuncio (senza punteggio)."""
    costo = cfg.costo_ristrutturazione(annuncio.mq, annuncio.condizione)
    valutazione = Valutazione(
        annuncio=annuncio,
        costo_ristrutturazione=costo,
        costo_totale=annuncio.prezzo + costo,
    )

    if annuncio.condizione == "ristrutturare":
        mq_usati = annuncio.mq or cfg.costi.mq_di_riferimento
        origine = "" if annuncio.mq else "mq stimati"
        costo_al_mq = migliaia(cfg.costi.per_livello(cfg.livello_per_caso_peggiore))
        valutazione.note.append(
            f"Ristrutturazione {cfg.livello_per_caso_peggiore}: {euro(costo)} "
            f"({mq_usati} mq × {costo_al_mq} €/mq{', ' + origine if origine else ''}) "
            f"→ totale {euro(valutazione.costo_totale)}"
        )
    elif annuncio.condizione == "parziale":
        valutazione.note.append(
            f"Lavori leggeri stimati in {euro(costo)} → totale {euro(valutazione.costo_totale)}"
        )
    elif annuncio.condizione == "unknown":
        valutazione.note.append(
            "La scheda non dichiara la manutenzione: il totale potrebbe salire "
            "in base ai lavori necessari."
        )

    if annuncio.prezzo > cfg.budget:
        valutazione.note.append(
            f"Prezzo {euro(annuncio.prezzo - cfg.budget)} oltre il budget: trattabile "
            f"solo con trattativa (tetto di ricerca {euro(cfg.prezzo_max_ricerca)})."
        )

    if annuncio.locali is None:
        valutazione.note.append("Locali non dichiarati nella scheda: verificare in pagina.")
    if annuncio.mq is None:
        valutazione.note.append("Superficie non dichiarata nella scheda.")
    if not annuncio.url:
        valutazione.note.append("Link dell'annuncio non recuperato.")

    if cfg.richiedi_condizione and annuncio.condizione == "unknown":
        valutazione.motivi_esclusione.append("manutenzione non dichiarata")

    return valutazione


def _filtra_ammissibili(valutazioni: list[Valutazione], cfg: Config) -> list[Valutazione]:
    """Esclude ciò che non rientra, annotando il motivo."""
    superstiti: list[Valutazione] = []
    for v in valutazioni:
        annuncio = v.annuncio
        v.motivi_esclusione.clear()

        if annuncio.prezzo > cfg.prezzo_max_ricerca:
            v.motivi_esclusione.append(
                f"prezzo {euro(annuncio.prezzo)} oltre il tetto di ricerca "
                f"({euro(cfg.prezzo_max_ricerca)})"
            )
        if annuncio.locali is not None and annuncio.locali < cfg.locali_minimi:
            v.motivi_esclusione.append(
                f"solo {annuncio.locali} locali (minimo {cfg.locali_minimi})")
        if cfg.mq_minimi is not None and annuncio.mq is not None and annuncio.mq < cfg.mq_minimi:
            v.motivi_esclusione.append(
                f"superficie {annuncio.mq} mq sotto il minimo {cfg.mq_minimi}")
        if v.costo_totale > cfg.prezzo_max_ricerca:
            v.motivi_esclusione.append(
                f"costo complessivo {euro(v.costo_totale)} oltre il tetto di ricerca "
                f"({euro(cfg.prezzo_max_ricerca)})"
            )

        if v.ammissibile:
            superstiti.append(v)
    return superstiti


# ─── Secondo passaggio: il punteggio ────────────────────────────────────────────


def _punteggio_eur_mq(prezzo_al_mq: int, mediana: float) -> float:
    if mediana <= 0:
        return 0.0
    scarto = (mediana - prezzo_al_mq) / mediana
    return max(-1.0, min(1.0, scarto))


def punteggia(valutazioni: list[Valutazione], cfg: Config) -> None:
    """Assegna il punteggio 0-100. La mediana €/mq è calcolata sul lotto trovato."""
    validi = [v.prezzo_al_mq for v in valutazioni if v.prezzo_al_mq]
    mediana = statistics.median(validi) if validi else 0.0

    for v in valutazioni:
        annuncio = v.annuncio
        motivi: list[str] = []

        # Quanto resta del budget, ristrutturazione compresa.
        margine = (cfg.budget - v.costo_totale) / cfg.budget
        contributo_budget = max(-1.0, min(1.0, margine / 0.3)) * PESO_BUDGET
        motivi.append(f"margine di budget {margine:+.0%}")

        # Prezzo al mq rispetto alla mediana dei risultati trovati.
        contributo_mq = 0.0
        if annuncio.prezzo_al_mq and mediana:
            contributo_mq = _punteggio_eur_mq(annuncio.prezzo_al_mq, mediana) * PESO_EURO_MQ
            motivi.append(
                f"{migliaia(annuncio.prezzo_al_mq)} €/mq contro una mediana di "
                f"{migliaia(mediana)} €/mq"
            )

        # Superficie vicina a quella ideale per il numero di locali richiesto.
        contributo_mq_tot = 0.0
        if annuncio.mq:
            scarto = abs(annuncio.mq - cfg.mq_ideale) / cfg.mq_ideale
            contributo_mq_tot = max(0.0, 1.0 - scarto) * PESO_SUPERFICIE
            motivi.append(f"superficie {annuncio.mq} mq (ideale {cfg.mq_ideale})")

        contributo_condizione = (
            PUNTEGGIO_CONDIZIONE.get(annuncio.condizione, 0.25) * PESO_CONDIZIONE
        )
        motivi.append(f"manutenzione: {annuncio.etichetta_condizione.lower()}")

        contributo_dati = 0.0
        if annuncio.locali is not None and annuncio.mq is not None:
            contributo_dati = PESO_COMPLETEZZA
            motivi.append("scheda completa (locali e mq presenti)")

        v.punteggio = max(0.0, min(100.0, 50 + contributo_budget + contributo_mq
                                   + contributo_mq_tot + contributo_condizione + contributo_dati))
        v.motivi_punteggio = motivi


def seleziona(valutazioni: list[Valutazione], cfg: Config) -> list[Valutazione]:
    """Filtra gli ammissibili, assegna il punteggio e ordina."""
    ammissibili = _filtra_ammissibili(valutazioni, cfg)
    punteggia(ammissibili, cfg)
    ammissibili.sort(key=lambda v: (-v.punteggio, v.costo_totale, v.prezzo))
    return ammissibili


def _completezza(annuncio: Annuncio) -> int:
    return sum(x is not None for x in (annuncio.locali, annuncio.mq, annuncio.piano, annuncio.url))


def valuta_tutti(annunci: list[Annuncio], cfg: Config) -> list[Valutazione]:
    """Valuta e deduplica tutti gli annunci, senza ancora filtrarli."""
    unici: dict[str, Valutazione] = {}
    for annuncio in annunci:
        valutazione = valuta(annuncio, cfg)
        chiave = f"{annuncio.fonte}|{annuncio.chiave()}"
        esistente = unici.get(chiave)
        if esistente is None:
            unici[chiave] = valutazione
        elif _completezza(annuncio) > _completezza(esistente.annuncio):
            # Stesso annuncio letto due volte: tieni la versione più completa.
            unici[chiave] = valutazione
    return list(unici.values())


def riepilogo_scarti(valutazioni: list[Valutazione]) -> dict[str, int]:
    """Conta gli annunci scartati, raggruppati per tipo di motivo."""
    conteggio: dict[str, int] = {}
    for v in valutazioni:
        if v.ammissibile:
            continue
        chiave = " · ".join(motivo.split("(")[0].strip() for motivo in v.motivi_esclusione)
        conteggio[chiave] = conteggio.get(chiave, 0) + 1
    return conteggio
