# cerca-casa-roma

Cercha case in vendita a Roma per **budget totale** (prezzo + ristrutturazione),
numero di locali e zona, e stima quanto costerà mettere a posto l'immobile
prima di andarci ad abitare.

```bash
python3 cerca_casa.py
```

Senza parametri cerca 3+ locali a Torrino entro 350.000 €.

## Installazione

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Oppure, in un colpo solo con [uv](https://docs.astral.sh/uv/):

```bash
uv venv && uv pip install -r requirements.txt
```

## Come ragiona

Il prezzo di acquisto da solo inganna: un appartamento economico da
ristrutturare può costare più di uno già pronto. Per ogni annuncio lo strumento

1. legge prezzo, locali, superficie e **condizione di manutenzione** dichiarata;
2. classifica la manutenzione in `ottimo`, `parziale`, `da ristrutturare`
   o `da verificare` (se la scheda non dice nulla);
3. somma il costo dei lavori stimato sulla superficie;
4. scarta ciò che non entra nel budget, **spiegando ogni scarto**.

### Budget e margine di trattativa

Il default è budget `350.000 €` con un margine di trattativa del 12 %, quindi
il tetto di ricerca è `392.000 €`. Gli immobili tra budget e tetto restano in
elenco con l'etichetta `trattativa`. Sopra il tetto vengono scartati.

Con ristrutturazione media (700 €/mq), un immobile da 75 mq richiede circa
52.500 € di lavori: per restare entro 350.000 € il prezzo di acquisto non può
superare **297.500 €**.

### Costi al mq

| Fascia            | €/mq | Cosa copre                              |
| ----------------- | ---- | --------------------------------------- |
| leggera           | 350  | tinteggiatura, piccoli interventi        |
| media (default)   | 700  | bagni, cucina, impianti parziali        |
| completa          | 1100 | tutto da rifare (impianti + finiture)   |

La mancanza della superficie non è un problema: si assume un appartamento
medio di 75 mq, indicato nel riepilogo finale. La classificazione della
manutenzione è conservativa: in caso di testo contraddittorio vince il caso
peggiore, e parole generiche come "moderno" o "recente" vengono ignorate
perché non distinguono nulla.

## Uso

```bash
# zona e budget diversi, anche più zone insieme
python3 cerca_casa.py --zona eur --zona trieste --budget 400000

# solo immobili da ristrutturare, in ordine di costo complessivo
python3 cerca_casa.py --solo-da-ristrutturare

# solo le schede che dichiarano la manutenzione
python3 cerca_casa.py --richiedi-condizione

# i link da aprire a mano, senza scaricare nulla
python3 cerca_casa.py --links
```

### Opzioni principali

| Opzione                   | Effetto                                                     |
| ------------------------- | ----------------------------------------------------------- |
| `--budget €`              | budget totale, ristrutturazione compresa                     |
| `--locali N`              | numero minimo di locali                                       |
| `--zona NOME`             | `eur`, `montesacro`, `torrino`, `torrino-mezzocammino`, `trieste` (ripetibile) |
| `--mq-ideale` / `--mq-minimo` | superficie ideale nel punteggio / scarto minimo             |
| `--pagine N`              | pagine di risultati da leggere per sito e zona               |
| `--margine FRAC`          | quota sopra il budget ammessa per la trattativa (`0.12`)     |
| `--solo-da-ristrutturare` | tieni solo gli immobili da ristrutturare                      |
| `--richiedi-condizione`   | scarta chi non dichiara la manutenzione                      |
| `--ristrutturazione`      | `leggera`, `media`, `completa`                               |
| `--eur-mq`                | costo al mq delle tre fasce                                  |
| `--mq-riferimento`        | superficie usata se la scheda non la dichiara                |
| `--timeout`, `--tentativi`, `--pausa` | comportamento di rete                              |
| `--links`                 | stampa i link di ricerca, senza scaricare                    |
| `--top N`                 | quanti annunci mostrare per categoria                        |
| `--output` / `--csv`      | esporta i risultati in JSON / CSV                            |
| `--no-salva`, `--no-color`, `--verbose` | output e diagnostica                 |

`--help` elenca tutto.

## Output

A terminale gli annunci sono divisi in tre gruppi — **pronti ad abitare**,
**da ristrutturare**, **condizione da verificare** — con punteggio,
costo complessivo e le note di cosa manca nella scheda. In fondo il riepilogo
dei costi usati.

I risultati si salvano in `risultati_casa.json` (con le impostazioni usate, i
problemi incontrati e le scelte fatte) e su richiesta in CSV con `--csv`.
`--no-salva` non scrive nulla.

## Portali e blocchi anti-bot

Il progetto interroga immobiliare.it, idealista.it e casa.it; per subito.it
stampa solo i link, perché non è previsto alcuno scraping automatico.

I portali rispondono spesso `HTTP 403` alle richieste automatizzate. Quando
succede lo strumento non si arrende in silenzio: dice quale sito ha bloccato la
richiesta e propone `--links` per la ricerca manuale. È un comportamento
atteso, non un errore.

I selettori dei portali cambiano spesso: se improvvisamente non trova
schede, il messaggio lo segnala esplicitamente. Le regole di parsing stanno
in `romasearch/parsing.py`, i selettori in `romasearch/scrapers/`.

## Sviluppo

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -q
.venv/bin/ruff check .
```

I test non fanno richieste di rete: lavorano su HTML di esempio e verificano
parsing, stima dei costi, selettori, costruzione degli URL, retry e CLI.

## Struttura

```
cerca_casa.py            entrypoint
romasearch/
  config.py              zone, costi, budget, validazione degli argomenti
  models.py              annuncio, deduplica
  parsing.py             prezzo, locali, mq, piano, condizione
  valutazione.py         costi, filtri, punteggio, motivi di scarto
  http.py                sessione, retry, rate limit, blocchi anti-bot
  formato.py             numeri ed euro in formato italiano
  report.py              output terminale, JSON, CSV
  cli.py                 argomenti e orchestrazione
  scrapers/              un modulo per portale, con selettori e URL
tests/                   test con pytest
```
