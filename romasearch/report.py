"""Output: riepilogo a terminale ed esportazione JSON/CSV."""

from __future__ import annotations

import csv
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO

from .config import Config
from .formato import euro, migliaia
from .scrapers import link_ricerca
from .valutazione import Valutazione

COLONNE_CSV = (
    "punteggio", "titolo", "prezzo", "costo_ristrutturazione", "costo_totale",
    "prezzo_al_mq", "locali", "mq", "piano", "condizione", "indirizzo", "fonte", "url",
)


class Colori:
    disattivati = False

    @classmethod
    def attiva(cls, attivo: bool) -> None:
        cls.disattivati = not attivo

    @classmethod
    def _(cls, codice: str, testo: str) -> str:
        return testo if cls.disattivati else f"\033[{codice}m{testo}\033[0m"


def verde(testo: str) -> str:
    return Colori._("92", testo)


def giallo(testo: str) -> str:
    return Colori._("93", testo)


def rosso(testo: str) -> str:
    return Colori._("91", testo)


def ciano(testo: str) -> str:
    return Colori._("96", testo)


def grassetto(testo: str) -> str:
    return Colori._("1", testo)


SEPARATORE = "─" * 72


# ─── Terminale ──────────────────────────────────────────────────────────────────


def stampa_risultati(
    out: TextIO,
    valutazioni: list[Valutazione],
    cfg: Config,
    problemi: list[str] | None = None,
    limite: int | None = None,
) -> None:
    zone = ", ".join(z.etichetta for z in cfg.zone_risolte)
    print(f"\n{grassetto('=' * 72)}", file=out)
    print(f"  RICERCA CASA — ROMA: {zone}", file=out)
    print(f"  Budget {euro(cfg.budget)} · min {cfg.locali_minimi} locali · "
          f"tetto ricerca {euro(cfg.prezzo_max_ricerca)}", file=out)
    print(f"  Annunci compatibili: {len(valutazioni)}", file=out)
    print(f"{grassetto('=' * 72)}\n", file=out)

    if not valutazioni:
        _stampa_nessun_risultato(out, cfg, problemi)
        return

    for titolo_sezione, lista in _sezioni(valutazioni):
        if not lista:
            continue
        print(f"\n{grassetto(titolo_sezione)}", file=out)
        print(SEPARATORE, file=out)
        for indice, v in enumerate(lista[:limite] if limite else lista, 1):
            _stampa_annuncio(out, indice, v, cfg)
        if limite and len(lista) > limite:
            print(f"  … altri {len(lista) - limite} annunci nella stessa categoria "
                  f"(usa --top 0 per vederli tutti)", file=out)
        print(file=out)

    _stampa_riepilogo(out, valutazioni, cfg)


def _sezioni(valutazioni: list[Valutazione]) -> list[tuple[str, list[Valutazione]]]:
    ordini = [
        ("ottimo", verde("PRONTI AD ABITARE / RISTRUTTURATI")),
        ("parziale", giallo("PARZIALMENTE RISTRUTTURATI")),
        ("ristrutturare", giallo("DA RISTRUTTURARE")),
        ("unknown", ciano("CONDIZIONE DA VERIFICARE")),
    ]
    return [(titolo, [v for v in valutazioni if v.annuncio.condizione == condizione])
            for condizione, titolo in ordini]


def _stampa_annuncio(out: TextIO, indice: int, v: Valutazione, cfg: Config) -> None:
    a = v.annuncio
    colore_prezzo = verde if a.prezzo <= cfg.budget else giallo

    print(f"\n{grassetto(f'[{indice}] {a.titolo}')}", file=out)
    print(f"    punteggio    {v.punteggio:5.1f}/100", file=out)
    print(f"    prezzo       {colore_prezzo(euro(a.prezzo) + _suffisso(v))}", file=out)
    dettagli = []
    if a.locali:
        dettagli.append(f"{a.locali} locali")
    if a.mq:
        dettagli.append(f"{a.mq} mq")
    if a.prezzo_al_mq:
        dettagli.append(f"{migliaia(a.prezzo_al_mq)} €/mq")
    if a.piano:
        dettagli.append(f"piano {a.piano}")
    if dettagli:
        print(f"    caratteri    {' · '.join(dettagli)}", file=out)
    print(f"    manutenzione {a.etichetta_condizione}", file=out)
    print(f"    dove         {a.indirizzo}", file=out)
    if a.url:
        print(f"    fonte        {a.fonte} — {a.url}", file=out)
    else:
        print(f"    fonte        {a.fonte} (link non recuperato)", file=out)
    if a.segnali_condizione:
        print(f"    segnali      {'; '.join(a.segnali_condizione[:3])}", file=out)
    for nota in v.note:
        print(f"    {giallo('·')} {nota}", file=out)


def _suffisso(v: Valutazione) -> str:
    if not v.costo_ristrutturazione:
        return ""
    return f"  +  {euro(v.costo_ristrutturazione)} lavori  =  {euro(v.costo_totale)}"


def _stampa_nessun_risultato(out: TextIO, cfg: Config, problemi: list[str] | None) -> None:
    print(rosso("Nessun annuncio compatibile con i criteri."), file=out)
    if problemi:
        print("\nCause probabili durante la raccolta:", file=out)
        for problema in problemi:
            print(f"  - {problema}", file=out)
    print("\nProva a rivedere i filtri o apri direttamente i link:", file=out)
    stampa_link(out, cfg)


def _stampa_riepilogo(out: TextIO, valutazioni: list[Valutazione], cfg: Config) -> None:
    print(f"\n{grassetto('=' * 72)}", file=out)
    print("  COSTI DI RISTRUTTURAZIONE USATI", file=out)
    print(grassetto("=" * 72), file=out)
    destinazioni = {
        "leggera": "tinteggiatura, piccoli interventi",
        "media": "bagni, cucina, impianti parziali",
        "completa": "tutto da rifare (impianti + finiture)",
    }
    for livello in ("leggera", "media", "completa"):
        costo = cfg.costi.per_livello(livello)
        marca = " ← applicata ai casi 'da ristrutturare'" if (
            livello == cfg.livello_per_caso_peggiore) else ""
        print(f"  {livello:<9} {costo:>5} €/mq   {destinazioni[livello]}{marca}", file=out)
    mq = cfg.costi.mq_di_riferimento
    print(f"\n  Su {mq} mq: {euro(mq * cfg.costi.leggera)} · "
          f"{euro(mq * cfg.costi.media)} · {euro(mq * cfg.costi.completa)}", file=out)
    print(f"  Per mantenere il budget di {euro(cfg.budget)} con ristrutturazione "
          f"{cfg.livello_per_caso_peggiore}, il prezzo di acquisto non può superare "
          f"{euro(cfg.prezzo_max_da_ristrutturare)}.", file=out)

    migliori = sorted(valutazioni, key=lambda v: v.costo_totale)[:3]
    if migliori:
        print("\n  A minor costo complessivo:", file=out)
        for v in migliori:
            a = v.annuncio
            print(f"    {euro(v.costo_totale):>12}  {a.titolo[:44]}"
                  f"  ({euro(a.prezzo)} + {euro(v.costo_ristrutturazione)})", file=out)
    print("\n  Verifica sempre la classe energetica, lo stato delle scale e la "
          "spesa condominiale in pagina.\n", file=out)


def stampa_link(out: TextIO, cfg: Config) -> None:
    print(f"\n{grassetto('=' * 72)}", file=out)
    print(f"  LINK DI RICERCA — budget {euro(cfg.budget)} · "
          f"tetto {euro(cfg.prezzo_max_ricerca)} "
          f"(+{cfg.margine_trattativa:.0%} di trattativa)", file=out)
    print(f"{grassetto('=' * 72)}\n", file=out)
    for indice, (nome, url) in enumerate(link_ricerca(cfg), 1):
        print(f"  {grassetto(f'[{indice}] {nome}')}", file=out)
        print(f"      {ciano(url)}\n", file=out)
    costo_mq = cfg.costi.per_livello(cfg.livello_per_caso_peggiore)
    print(f"  Nota: con ristrutturazione {cfg.livello_per_caso_peggiore} "
          f"({migliaia(costo_mq)} €/mq) un immobile da "
          f"{cfg.costi.mq_di_riferimento} mq richiede circa "
          f"{euro(cfg.costi.mq_di_riferimento * costo_mq)} di lavori: per stare nel "
          f"budget cercare fino a {euro(cfg.prezzo_max_da_ristrutturare)}.\n", file=out)


# ─── Esportazione ───────────────────────────────────────────────────────────────


@dataclass
class Metadati:
    """Contesto del run, salvato accanto ai risultati."""

    config: Config
    per_sito: dict[str, int]
    problemi: list[str]
    annunci_letti: int

    def to_dict(self) -> dict:
        return {
            "generato_il": _adesso(),
            "query": {
                "budget": self.config.budget,
                "tetto_ricerca": self.config.prezzo_max_ricerca,
                "locali_minimi": self.config.locali_minimi,
                "mq_ideale": self.config.mq_ideale,
                "zone": list(self.config.zone),
                "livello_ristrutturazione": self.config.livello_per_caso_peggiore,
                "costi_eur_mq": {
                    "leggera": self.config.costi.leggera,
                    "media": self.config.costi.media,
                    "completa": self.config.costi.completa,
                },
            },
            "annunci_letti": self.annunci_letti,
            "annunci_per_sito": self.per_sito,
            "problemi": self.problemi,
        }


def _adesso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def esporta_json(path: Path, valutazioni: list[Valutazione], meta: Metadati) -> None:
    dati = {
        "meta": meta.to_dict(),
        "risultati": [v.to_dict() for v in valutazioni],
    }
    path.write_text(json.dumps(dati, ensure_ascii=False, indent=2), encoding="utf-8")


def esporta_csv(path: Path, valutazioni: list[Valutazione]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        scrittore = csv.DictWriter(f, fieldnames=list(COLONNE_CSV), extrasaction="ignore")
        scrittore.writeheader()
        for v in valutazioni:
            riga = v.to_dict()
            riga["punteggio"] = round(v.punteggio, 1)
            scrittore.writerow(riga)


def colore_attivo() -> bool:
    return sys.stdout.isatty() and not os.environ.get("NO_COLOR")
