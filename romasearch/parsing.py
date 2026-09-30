"""Estrazione dei dati dalle schede degli annunci (testo -> campi strutturati).

Funzioni pure, senza dipendenze: sono il cuore del progetto e sono coperte dai
test. Ogni regex è pensata per non produrre falsi positivi sui testi reali dei
portali ("350.000 € 120 €/mq", "3 locali 90 mq", "piano 3 di 6", ...).
"""

from __future__ import annotations

import re
import unicodedata

PREZZO_MIN = 20_000
PREZZO_MAX = 20_000_000

# ─── Normalizzazione ────────────────────────────────────────────────────────────

_SEPARATORS = re.compile(r"\s+")


def normalizza(testo: str) -> str:
    """Minuscolo, senza accenti e senza spazi superflui."""
    decompresso = unicodedata.normalize("NFKD", (testo or "").lower())
    senza_accenti = "".join(c for c in decompresso if not unicodedata.combining(c))
    return _SEPARATORS.sub(" ", senza_accenti).strip()


# ─── Prezzo ─────────────────────────────────────────────────────────────────────

# "1.250 €/mq", "350 euro/metro quadro": vanno rimossi prima di cercare il prezzo.
_RE_PREZZO_AL_MQ = re.compile(
    r"\d[\d.\s'’]*\s*(?:€|eur|euro)?\s*(?:/|al|,)\s*(?:mq|m\s?[²2q]|metro[ ]quadr[oi])"
)
# "350.000 €", "350000 euro"
_RE_PREZZO_SIMBOLO = re.compile(r"(\d[\d.\s'’]*)\s*(?:€|eur|euro)(?![a-z])")
# "Prezzo: 350.000", "price 350000"
_RE_PREZZO_PREFFISSO = re.compile(r"\b(?:prezzo|price)\b\D{0,12}?(\d[\d.\s'’]*)")
# Numero con separatori delle migliaia senza simbolo: "350.000", "350 000"
_RE_PREZZO_GRANDE = re.compile(r"(?<![\d.,])(\d{1,3}(?:[.\s'’]\d{3}){1,3})(?![\d,])")
# Ultimo risorsa: numero secco di 5-8 cifre. La soglia minima (20.000) esclude
# i CAP di 5 cifre, che altrimenti verrebbero scambiati per un prezzo.
_RE_PREZZO_NUMERO = re.compile(r"(?<![\d.,])(\d{5,8})(?![\d,])")


def _a_intero(testo: str) -> int | None:
    """'350.000' -> 350000, '1.250,50' -> 1250, '350 000' -> 350000."""
    t = re.sub(r"[^\d]", "", testo)
    return int(t) if t else None


def estrai_prezzo(testo: str) -> int | None:
    """Prezzo di vendita in euro, o None se non dichiarato ('su richiesta' ecc.)."""
    t = normalizza(testo)
    t = _RE_PREZZO_AL_MQ.sub(" ", t)

    for regex in (_RE_PREZZO_SIMBOLO, _RE_PREZZO_PREFFISSO, _RE_PREZZO_GRANDE,
                  _RE_PREZZO_NUMERO):
        m = regex.search(t)
        if not m:
            continue
        valore = _a_intero(m.group(1))
        if valore is not None and PREZZO_MIN <= valore <= PREZZO_MAX:
            return valore
    return None


# ─── Locali ─────────────────────────────────────────────────────────────────────

_MAPPA_LOCALI = {
    "monolocale": 1,
    "bilocale": 2,
    "trilocale": 3,
    "quadrilocale": 4,
    "quinquilocale": 5,
    "sestilocale": 6,
    "settilocale": 7,
    "ottilocale": 8,
}

_RE_LOCALI_NOME = re.compile(r"\b(?:" + "|".join(_MAPPA_LOCALI) + r")\b")
_RE_NUMERO_LOCALI = re.compile(r"(\d{1,2})\s*(?:\+|plus)?\s*(?:local[ei]|vani)\b")
_RE_LOCALI_NUMERO = re.compile(r"\blocal[ei]\s*:?\s*(\d{1,2})\b")
_RE_VANI = re.compile(r"\b(?:in\s+|circa\s+)?(\d{1,2})\s*vani\b")
_RE_VANI_NUMERO = re.compile(r"\bvani\s*:?\s*(\d{1,2})\b")


def estrai_locali(testo: str) -> int | None:
    """Numero di locali (vani) dichiarato nella scheda, o None."""
    t = normalizza(testo)

    m = _RE_LOCALI_NOME.search(t)
    if m:
        return _MAPPA_LOCALI[m.group(0)]

    for regex in (_RE_NUMERO_LOCALI, _RE_LOCALI_NUMERO, _RE_VANI, _RE_VANI_NUMERO):
        m = regex.search(t)
        if m:
            valore = int(m.group(1))
            if 1 <= valore <= 15:
                return valore
    return None


# ─── Superficie ─────────────────────────────────────────────────────────────────

# "90 mq", "90 m²", "90mq", "90 metri quadri". Non deve agganciare "350 €/mq"
# perché lì il numero è preceduto dal simbolo e non seguito da "mq".
_RE_MQ = re.compile(
    r"(?<![\d.,])(\d{2,4})\s*(?:m\s?[²2q]|mq|metri\s+quadr[oi])\b",
    re.IGNORECASE,
)


def estrai_mq(testo: str) -> int | None:
    """Superficie in mq, o None se non dichiarata o implausibile."""
    for m in _RE_MQ.finditer(testo):
        valore = _a_intero(m.group(1))
        if valore is not None and 20 <= valore <= 1_000:
            return valore
    return None


# ─── Piano ──────────────────────────────────────────────────────────────────────

_RE_PIANO_NUMERO = re.compile(r"\b(?:piano\s*:?\s*(\d{1,2})|(\d{1,2})\s*(?:°|o)?\s*piano\b)")
_RE_PIANI_PAROLA = re.compile(
    r"\b(?:piano\s+)?(seminterrato|rialzato|terra|ultimo|quinto|quarto|terzo|secondo|primo)"
    r"(?:\s+piano)?\b"
)

_PIANI_PAROLA = {
    "seminterrato": "seminterrato",
    "rialzato": "rialzato",
    "terra": "terra",
    "ultimo": "ultimo",
    "quinto": "5",
    "quarto": "4",
    "terzo": "3",
    "secondo": "2",
    "primo": "1",
}


def estrai_piano(testo: str) -> str | None:
    """Piano come testo normalizzato ('terra', 'rialzato', 'ultimo', '3')."""
    t = normalizza(testo)

    m = _RE_PIANI_PAROLA.search(t)
    if m and m.group(1) in _PIANI_PAROLA:
        return _PIANI_PAROLA[m.group(1)]

    m = _RE_PIANO_NUMERO.search(t)
    if m:
        numero = m.group(1) or m.group(2)
        valore = int(numero)
        if 1 <= valore <= 30:
            return str(valore)
    return None


# ─── Condizione di manutenzione ──────────────────────────────────────────────────
#
# Le regole sono valutate in ordine: la prima che trova un segnale vince. In
# particolare "parzialmente ristrutturato" contiene "ristrutturato", quindi il
# gruppo PARZIALE deve precedere quello POSITIVO; e "da ristrutturare" vince
# su tutto, perché in caso di testi contraddittori conviene il caso peggiore.
#
# Sono stati volutamente esclusi termini come "lavori", "arredato", "moderno",
# "recente", "pregio", "di lusso", "originale": compaiono nella quasi totalità
# delle schede e non discriminano nulla (nella versione precedente facevano
# classificare come "ottimo" anche gli immobili da ristrutturare).

# "ristrutturare" e "ristrutturato" hanno terminazioni diverse: serve un
# prefisso comune esplicito invece di una classe di caratteri che taglierebbe
# "ristrutturare" su "ristrutturat".
_RISTR = r"(?:ristrutturat[oa]\b|ristrutturar(?:e|si|no)\b)"

# Ogni segnale è (etichetta leggibile, espressione regolare): l'etichetta viene
# mostrata all'utente, così la classificazione è ispezionabile a colpo d'occhio.
_GRUPPO_RISTRUTTURARE = (
    ("non ristrutturato", rf"\b(?:non|mai)\s+{_RISTR}"),
    ("da ristrutturare", rf"\bda\s+{_RISTR}"),
    ("da rinnovare o riqualificare",
     r"\bda\s+(?:rinnovare|riqualificare|sistemare|rimodernare|recuperare|rifare)\w*"),
    ("necessita lavori", r"\bnecessita\s+(?:di\s+)?(?:lavori|interventi)\b"),
    ("impianti da rifare", r"\b(?:impianti|infissi|impianto|infisso)\s+da\s+rifare\b"),
    ("non abitabile", r"\bnon\s+abitabile\b"),
    ("lavori da eseguire", r"\blavori\s+da\s+eseguire\b"),
    ("manutenzione straordinaria", r"\bmanutenzione\s+straordinaria\b"),
)

_GRUPPO_PARZIALE = (
    ("parzialmente ristrutturato", rf"\bparzialmente\s+{_RISTR}"),
    ("semi-ristrutturato", rf"\b(?:semi|parziale)\s*-?\s*{_RISTR}"),
    ("ristrutturato in parte", rf"{_RISTR}\s+in\s+parte\b"),
    ("qualche intervento", r"\bqualche\s+(?:intervent|lavor)\w*\b"),
    ("da riqualificare in parte",
     r"\bda\s+(?:riqualificare|rinnovare)\s+(?:solo\s+)?in\s+parte\b"),
)

_GRUPPO_OTTIMO = (
    ("appena ristrutturato", rf"\b(?:appena|recentemente|nuovamente)\s+{_RISTR}"),
    ("finemente ristrutturato", rf"\bfinemente\s+{_RISTR}"),
    ("ristrutturazione recente",
     r"\b(?:ultima\s+)?ristrutturazione\s+(?:del\s+)?(?:19|20)\d{2}\b"),
    ("ristrutturato", r"\bristrutturat[oa]\b"),
    ("nuova costruzione", r"\bnuova\s+costruzion[ei]\b"),
    ("ottimo stato", r"\bottim[oae]\s+stato\b"),
    ("ottime condizioni", r"\b(?:in\s+)?ottim[oe]\s+condizion[ie]\b"),
    ("chiavi in mano", r"\bchiavi\s+in\s+mano\b"),
    ("rifinito", r"\brifinit[oi]\b"),
    ("poco usato", r"\bpoco\s+usat[oa]\b"),
    ("nuovo", r"\bnuov[oa]\b"),
)

_GRUPPI = (
    ("ristrutturare", _GRUPPO_RISTRUTTURARE),
    ("parziale", _GRUPPO_PARZIALE),
    ("ottimo", _GRUPPO_OTTIMO),
)


def analizza_condizione(testo: str) -> tuple[str, list[str]]:
    """Classifica la manutenzione dichiarata.

    Restituisce ``(condizione, segnali)`` con condizione in
    ``ottimo`` | ``parziale`` | ``ristrutturare`` | ``unknown`` e segnali
    leggibili ("da ristrutturare", "chiavi in mano", ...).
    """
    t = normalizza(testo)
    for condizione, segnali in _GRUPPI:
        trovati = [etichetta for etichetta, schema in segnali if re.search(schema, t)]
        if trovati:
            return condizione, trovati
    return "unknown", []


# ─── Estrazione completa ────────────────────────────────────────────────────────


def estrai_dalla_scheda(testo: str) -> dict:
    """Estrae tutti i campi da un blocco di testo di una scheda."""
    condizione, segnali = analizza_condizione(testo)
    return {
        "prezzo": estrai_prezzo(testo),
        "locali": estrai_locali(testo),
        "mq": estrai_mq(testo),
        "piano": estrai_piano(testo),
        "condizione": condizione,
        "segnali_condizione": segnali,
    }
