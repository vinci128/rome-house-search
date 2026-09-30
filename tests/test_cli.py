"""Test della CLI: opzioni, output, --links, esportazione."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from romasearch import cli
from romasearch.models import Annuncio
from romasearch.scrapers import Raccolta


@pytest.fixture
def raccolta_finta(monkeypatch):
    annunci = [
        Annuncio(titolo="Quadrilocale ristrutturato", prezzo=290_000, fonte="immobiliare.it",
                 url="https://www.immobiliare.it/annunci/1/", zona="torrino",
                 indirizzo="Via D'Iliria", locali=4, mq=100, condizione="ottimo"),
        Annuncio(titolo="Trilocale da ristrutturare", prezzo=250_000, fonte="idealista.it",
                 url="https://www.idealista.it/immobile/2/", zona="torrino",
                 indirizzo="Via Giordani", locali=3, mq=90, condizione="ristrutturare"),
        Annuncio(titolo="Bilocale scartato", prezzo=300_000, fonte="casa.it",
                 url="https://www.casa.it/immobile/3/", zona="torrino",
                 locali=2, mq=60),
    ]
    raccolta = Raccolta(
        annunci=annunci,
        per_sito={"immobiliare.it": 1, "idealista.it": 1, "casa.it": 1},
    )
    monkeypatch.setattr(cli, "raccogli", lambda cfg, sessione=None: raccolta)
    return raccolta


# ─── Opzioni ────────────────────────────────────────────────────────────────────


def test_predefiniti():
    cfg = cli.config_da_argomenti(cli.costruisci_parser().parse_args([]))
    assert cfg.budget == 350_000
    assert cfg.locali_minimi == 3
    assert cfg.zone == ("torrino",)
    assert cfg.costi.media == 700


def test_opzioni_cambiano_la_configurazione():
    args = cli.costruisci_parser().parse_args([
        "--budget", "250000", "--locali", "4", "--zona", "eur", "--zona", "montesacro",
        "--mq-minimo", "80", "--pagine", "3", "--margine", "0.2",
        "--ristrutturazione", "completa", "--eur-mq", "300", "600", "900",
        "--mq-riferimento", "90", "--pausa", "0", "--tentativi", "1",
    ])
    cfg = cli.config_da_argomenti(args)
    assert cfg.budget == 250_000
    assert cfg.locali_minimi == 4
    assert cfg.zone == ("eur", "montesacro")
    assert cfg.mq_minimi == 80
    assert cfg.pagine_per_zona == 3
    assert cfg.prezzo_max_ricerca == 300_000
    assert cfg.livello_per_caso_peggiore == "completa"
    assert cfg.costi.leggera == 300
    assert cfg.costi.completa == 900
    assert cfg.costi.mq_di_riferimento == 90


def test_zona_ignota_esce_con_errore():
    with pytest.raises(SystemExit) as errore:
        cli.main(["--zona", "quartiere-inesistente"])
    assert errore.value.code == 2


def test_help_funziona():
    with pytest.raises(SystemExit) as errore:
        cli.main(["--help"])
    assert errore.value.code == 0


# ─── --links ────────────────────────────────────────────────────────────────────


def test_links_stampa_gli_url(capsys):
    assert cli.main(["--links", "--no-color"]) == 0
    out = capsys.readouterr().out
    assert "immobiliare.it" in out
    assert "idealista.it" in out
    assert "casa.it" in out
    assert "subito.it" in out
    assert "392.000 €" in out
    assert "297.500 €" in out


def test_links_rispettano_budget_e_zone(capsys):
    cli.main(["--links", "--no-color", "--budget", "250000", "--zona", "eur"])
    out = capsys.readouterr().out
    assert "eur-roma" in out
    assert "280000" in out


# ─── Esecuzione ─────────────────────────────────────────────────────────────────


def test_esecuzione_con_risultati(raccolta_finta, capsys):
    codice = cli.main(["--no-color", "--no-salva"])
    assert codice == 0
    cattura = capsys.readouterr()
    assert "Quadrilocale ristrutturato" in cattura.out
    assert "Trilocale da ristrutturare" in cattura.out
    assert "PRONTI AD ABITARE" in cattura.out
    assert "DA RISTRUTTURARE" in cattura.out
    # REGRESSIONE: il filtro sui locali deve funzionare e dichiarare lo scarto.
    assert "Bilocale scartato" not in cattura.out
    assert "locali" in cattura.err


def test_esecuzione_senza_risultati_mostra_i_link(monkeypatch, capsys):
    monkeypatch.setattr(cli, "raccogli",
                        lambda cfg, sessione=None: Raccolta(problemi=["bloccato"]))
    assert cli.main(["--no-color", "--no-salva"]) == 0
    out = capsys.readouterr().out
    assert "Nessun annuncio compatibile" in out
    assert "immobiliare.it" in out  # i link di riserva


def test_problemi_mostrati_solo_come_detto(raccolta_finta, capsys, tmp_path):
    cli.main(["--no-color", "--no-salva", "--output", str(tmp_path / "x.json")])
    assert "selettori" not in capsys.readouterr().err


def test_verboso_mostra_i_problemi(monkeypatch, capsys):
    raccolta = Raccolta(
        annunci=[Annuncio(titolo="A", prezzo=300_000, fonte="casa.it", locali=3, mq=90)],
        problemi=["casa.it: selettori da aggiornare"],
        per_sito={"casa.it": 1},
    )
    monkeypatch.setattr(cli, "raccogli", lambda cfg, sessione=None: raccolta)
    cli.main(["--no-color", "--no-salva", "--verbose"])
    assert "selettori da aggiornare" in capsys.readouterr().err


def test_esportazione_json(raccolta_finta, tmp_path):
    json_out = tmp_path / "risultati.json"
    cli.main(["--no-color", "--output", str(json_out), "--csv", str(tmp_path / "r.csv")])

    dati = json.loads(json_out.read_text(encoding="utf-8"))
    assert len(dati["risultati"]) == 2  # il bilocale è scartato
    primo = dati["risultati"][0]
    for campo in ("titolo", "prezzo", "costo_totale", "punteggio", "motivi_punteggio",
                  "condizione", "ammissibile"):
        assert campo in primo, campo
    assert dati["meta"]["query"]["budget"] == 350_000
    assert dati["meta"]["annunci_letti"] == 3
    assert dati["meta"]["annunci_per_sito"]["casa.it"] == 1

    csv_out = (tmp_path / "r.csv").read_text(encoding="utf-8").splitlines()
    assert csv_out[0].startswith("punteggio,titolo,prezzo")
    assert len(csv_out) == 3  # intestazione + 2 annunci


def test_no_salva_non_scrive(tmp_path, raccolta_finta):
    json_out = tmp_path / "risultati.json"
    cli.main(["--no-color", "--no-salva", "--output", str(json_out)])
    assert not json_out.exists()


def test_nessun_risultato_non_scrive_un_file_vuoto(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "raccogli", lambda cfg, sessione=None: Raccolta())
    json_out = tmp_path / "risultati.json"
    cli.main(["--no-color", "--output", str(json_out)])
    assert not json_out.exists()


def test_top_limitale_per_categoria(monkeypatch, capsys):
    annunci = [
        Annuncio(titolo=f"Pronto {i}", prezzo=300_000 + i, fonte="casa.it",
                 url=f"https://www.casa.it/{i}", zona="torrino", locali=3, mq=90,
                 condizione="ottimo")
        for i in range(3)
    ]
    monkeypatch.setattr(cli, "raccogli",
                        lambda cfg, sessione=None: Raccolta(annunci=annunci, per_sito={}))
    cli.main(["--no-color", "--no-salva", "--top", "1"])
    out = capsys.readouterr().out
    assert "Pronto 0" in out
    assert out.count("manutenzione Pronto / ristrutturato") == 1
    assert "altri 2 annunci" in out


def test_top_zero_mostra_tutto(monkeypatch, capsys):
    annunci = [
        Annuncio(titolo=f"Pronto {i}", prezzo=300_000 + i, fonte="casa.it",
                 url=f"https://www.casa.it/{i}", zona="torrino", locali=3, mq=90,
                 condizione="ottimo")
        for i in range(3)
    ]
    monkeypatch.setattr(cli, "raccogli",
                        lambda cfg, sessione=None: Raccolta(annunci=annunci, per_sito={}))
    cli.main(["--no-color", "--no-salva", "--top", "0"])
    assert "Pronto 2" in capsys.readouterr().out


def test_nessun_colore_senza_opzione(raccolta_finta, capsys):
    cli.main(["--no-salva", "--no-color"])
    assert "\033[" not in capsys.readouterr().out


def test_i_colori_si_possono_disattivare_anche_da_ambiente(raccolta_finta, capsys,
                                                           monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    cli.main(["--no-salva"])
    assert "\033[" not in capsys.readouterr().out


def test_config_da_argomenti_ricalcola_i_derivati():
    cfg = cli.config_da_argomenti(cli.costruisci_parser().parse_args(
        ["--budget", "500000", "--mq-riferimento", "100"]))
    assert cfg.prezzo_max_ricerca == 560_000
    assert cfg.prezzo_max_da_ristrutturare == 430_000


# ─── Dipendenze ──────────────────────────────────────────────────────────────────
#
# Caso reale: `python3 cerca_casa.py` con il Python di sistema invece di quello
# del virtualenv, che porta a un ModuleNotFoundError incomprensibile.

BLOCCA_DEPENDENZE = """
import sys

class _Bloccante:
    def find_spec(self, nome, percorso=None, target=None):
        radice = nome.split(".")[0]
        if radice in {"bs4", "lxml", "requests", "soupsieve"}:
            raise ModuleNotFoundError(f"No module named {nome!r}", name=nome)
        return None

sys.meta_path.insert(0, _Bloccante())
"""

ROOT = Path(__file__).resolve().parent.parent


def test_i_links_funzionano_senza_dipendenze_installate():
    """--links costruisce solo URL: non deve richiedere requests né bs4."""
    risultato = subprocess.run(
        [sys.executable, "-c",
         BLOCCA_DEPENDENZE + "\nimport runpy, sys; sys.argv = ['cerca_casa.py', '--links',"
         " '--no-color']; runpy.run_path('cerca_casa.py', run_name='__main__')"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert risultato.returncode == 0, risultato.stderr
    assert "LINK DI RICERCA" in risultato.stdout
    assert "immobiliare.it" in risultato.stdout


def test_lo_scraping_dichiara_le_dipendenze_mancanti():
    risultato = subprocess.run(
        [sys.executable, "-c",
         BLOCCA_DEPENDENZE + "\nimport runpy, sys; sys.argv = ['cerca_casa.py', '--zona',"
         " 'ostiense', '--no-color']; runpy.run_path('cerca_casa.py', run_name='__main__')"],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert risultato.returncode == 2
    assert "Dipendenze mancanti" in risultato.stderr
    assert "bs4" in risultato.stderr
    assert "--links" in risultato.stderr  # suggerisce la via che funziona comunque


def test_le_dipendenze_del_progetto_sono_installate_qui():
    """Nel virtualenv del progetto non deve mancare nulla."""
    assert cli._mancano_dipendenze() is False
