"""Interfaccia a riga di comando."""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from . import __version__, report
from .config import ZONE, Config, CostiRistrutturazione
from .formato import euro
from .report import Colori, Metadati
from .scrapers import Raccolta, raccogli
from .valutazione import riepilogo_scarti, seleziona, valuta_tutti

DEFAULT_OUTPUT = "risultati_casa.json"


def costruisci_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cerca_casa.py",
        description="Cerca casa a Roma per budget, locali e zona, stimando i costi "
                    "di ristrutturazione.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        epilog="Senza parametri cerca 3+ locali a Torrino entro 350.000€.",
    )
    parser.add_argument("--versione", action="version", version=f"%(prog)s {__version__}")

    ricerca = parser.add_argument_group("criteri di ricerca")
    ricerca.add_argument("--budget", type=int, default=350_000, metavar="€",
                         help="budget totale, ristrutturazione compresa")
    ricerca.add_argument("--locali", type=int, default=3, metavar="N",
                         help="numero minimo di locali")
    ricerca.add_argument("--zona", action="append", metavar="NOME", default=None,
                         help=f"zona da cercare, ripetibile; una di: {', '.join(sorted(ZONE))}")
    ricerca.add_argument("--mq-ideale", type=int, default=100, metavar="MQ",
                         help="superficie considerata ideale nel punteggio")
    ricerca.add_argument("--mq-minimo", type=int, default=None, metavar="MQ",
                         help="scarta gli immobili sotto questa superficie")
    ricerca.add_argument("--pagine", type=int, default=1, metavar="N",
                         help="pagine di risultati da leggere per zona e sito")
    ricerca.add_argument("--margine", type=float, default=0.12, metavar="FRAC",
                         help="quota sopra il budget ammessa per la trattativa (0.12 = 12%%)")
    ricerca.add_argument("--solo-da-ristrutturare", action="store_true",
                         help="cerca solo immobili da ristrutturare")
    ricerca.add_argument("--richiedi-condizione", action="store_true",
                         help="scarta gli annunci che non dichiarano la manutenzione")

    costi = parser.add_argument_group("costi di ristrutturazione")
    costi.add_argument("--ristrutturazione", choices=("leggera", "media", "completa"),
                       default="media",
                       help="fascia applicata agli immobili da ristrutturare")
    costi.add_argument("--eur-mq", type=int, nargs=3, metavar=("LEGGERA", "MEDIA", "COMPLETA"),
                       default=None, help="costo al mq per le tre fasce")
    costi.add_argument("--mq-riferimento", type=int, default=75, metavar="MQ",
                       help="superficie usata quando la scheda non dichiara i mq")

    rete = parser.add_argument_group("rete")
    rete.add_argument("--timeout", type=int, default=15, metavar="SEC")
    rete.add_argument("--tentativi", type=int, default=3, metavar="N",
                      help="tentativi per pagina in caso di errore")
    rete.add_argument("--pausa", type=float, default=1.5, metavar="SEC",
                      help="pausa minima tra due richieste allo stesso sito")

    uscita = parser.add_argument_group("uscita")
    uscita.add_argument("--links", action="store_true",
                        help="stampa i link di ricerca da aprire nel browser, senza scaricare")
    uscita.add_argument("--top", type=int, default=10, metavar="N",
                        help="quanti annunci mostrare per categoria (0 = tutti)")
    uscita.add_argument("--output", type=Path, default=Path(DEFAULT_OUTPUT), metavar="FILE",
                        help=f"file JSON dei risultati (predefinito: {DEFAULT_OUTPUT})")
    uscita.add_argument("--csv", type=Path, default=None, metavar="FILE",
                        help="esporta anche un CSV")
    uscita.add_argument("--no-salva", action="store_true", help="non scrivere file")
    uscita.add_argument("--no-color", action="store_true", help="output senza colori")
    uscita.add_argument("--verbose", "-v", action="store_true", help="mostra i problemi raccolti")
    return parser


def config_da_argomenti(args: argparse.Namespace) -> Config:
    costi = CostiRistrutturazione(
        *(args.eur_mq or (350, 700, 1100)),
        mq_di_riferimento=args.mq_riferimento,
    )
    return Config(
        budget=args.budget,
        locali_minimi=args.locali,
        mq_minimi=args.mq_minimo,
        mq_ideale=args.mq_ideale,
        margine_trattativa=args.margine,
        zone=tuple(args.zona) if args.zona else ("torrino",),
        pagine_per_zona=max(1, args.pagine),
        solo_ristrutturare=args.solo_da_ristrutturare,
        richiedi_condizione=args.richiedi_condizione,
        costi=costi,
        livello_per_caso_peggiore=args.ristrutturazione,
        timeout=args.timeout,
        tentativi=max(1, args.tentativi),
        pausa=max(0.0, args.pausa),
    )


def _mancano_dipendenze() -> bool:
    """True se manca qualcosa per leggere le pagine, spiegando come installarlo.

    Prima di scaricare: senza questi moduli non si può estrarre nulla, e
    fallire qui è molto più utile che fallire sul primo annuncio.
    """
    mancanti = []
    for modulo in ("requests", "bs4", "lxml"):
        try:
            importlib.import_module(modulo)
        except ImportError:
            mancanti.append(modulo)
    if not mancanti:
        return False

    print(f"\nDipendenze mancanti: {', '.join(mancanti)}.", file=sys.stderr)
    print("Installale con:", file=sys.stderr)
    print("    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt\n",
          file=sys.stderr)
    print(f"Python in uso: {sys.executable}", file=sys.stderr)
    print("Nel dubbio: --links funziona anche senza dipendenze.", file=sys.stderr)
    return True


def _segnala_problemi(raccolta: Raccolta, verboso: bool) -> None:
    """I problemi di raccolta, sempre se non è andato tutto bene."""
    if verboso or not raccolta.annunci:
        for problema in raccolta.problemi:
            print(f"  {report.giallo('!')} {problema}", file=sys.stderr)
    if any("bloccato" in p or "anti-bot" in p for p in raccolta.problemi):
        print(report.rosso("Alcuni portali hanno bloccato la raccolta automatica: "
                           "usa --links per la ricerca manuale."), file=sys.stderr)


def _salva(buone: list, raccolta: Raccolta, cfg: Config, args: argparse.Namespace) -> None:
    """Scrive JSON ed eventuale CSV, o spiega perché non c'è niente da salvare."""
    if args.no_salva or not buone:
        if not args.no_salva:
            print(f"Nessun annuncio da salvare in {args.output}.")
        return

    meta = Metadati(
        config=cfg,
        per_sito=raccolta.per_sito,
        problemi=raccolta.problemi,
        annunci_letti=len(raccolta.annunci),
    )
    report.esporta_json(args.output, buone, meta)
    scritti = [str(args.output)]
    if args.csv:
        report.esporta_csv(args.csv, buone)
        scritti.append(str(args.csv))
    print(f"Risultati salvati in {', '.join(scritti)} ({len(buone)} annunci)")


def main(argv: list[str] | None = None) -> int:
    parser = costruisci_parser()
    args = parser.parse_args(argv)

    try:
        cfg = config_da_argomenti(args)
    except (ValueError, KeyError) as exc:
        parser.error(str(exc))
        return 2

    Colori.attiva(not args.no_color and report.colore_attivo())

    if args.links:
        report.stampa_link(sys.stdout, cfg)
        return 0

    if _mancano_dipendenze():
        return 2

    zone = ", ".join(z.etichetta for z in cfg.zone_risolte)
    print(f"Ricerca casa a Roma — {zone}")
    print(f"Budget {euro(cfg.budget)} · tetto di ricerca {euro(cfg.prezzo_max_ricerca)} · "
          f"min {cfg.locali_minimi} locali")
    print("Interrogo i portali...\n")

    raccolta = raccogli(cfg)
    print(f"  {len(raccolta.annunci)} schede lette")
    for sito, totale in sorted(raccolta.per_sito.items()):
        print(f"    {sito:<18} {totale}")

    _segnala_problemi(raccolta, args.verbose)

    valutazioni = valuta_tutti(raccolta.annunci, cfg)
    buone = seleziona(valutazioni, cfg)
    # seleziona() compila i motivi di esclusione: va chiamata prima del riepilogo.
    scarti = riepilogo_scarti(valutazioni)

    report.stampa_risultati(
        sys.stdout, buone, cfg, problemi=raccolta.problemi, limite=args.top or None)

    if scarti:
        print(f"  Scartati {len(valutazioni) - len(buone)} annunci:", file=sys.stderr)
        for motivo, quanti in sorted(scarti.items(), key=lambda kv: -kv[1]):
            print(f"    {quanti:>3} × {motivo}", file=sys.stderr)
        print(file=sys.stderr)

    _salva(buone, raccolta, cfg, args)

    if not buone:
        print("Nessun risultato: prova  python3 cerca_casa.py --links  "
              "e apri i link nel browser.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
