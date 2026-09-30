"""Configurazione della ricerca: zone, costi di ristrutturazione, budget.

Tutti i valori che nel vecchio script erano costanti hardcoded (budget 350k,
12% di margine, 700 €/mq, la soglia "270k" degli annunci da ristrutturare)
vivono qui e sono sovrascrivibili da riga di comando.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

# Fasce di costo ristrutturazione in €/mq.
LIVELLI_RISTRUTTURAZIONE = ("leggera", "media", "completa")


@dataclass(frozen=True)
class Zona:
    """Una zona di ricerca e i suoi identificativi nei vari portali."""

    nome: str
    etichetta: str
    slug_immobiliare: str
    slug_idealista: str
    ricerca_casa: str
    indirizzo_fallback: str


ZONE: dict[str, Zona] = {
    "torrino": Zona(
        nome="torrino",
        etichetta="Torrino (quartiere EUR)",
        slug_immobiliare="torrino-roma",
        slug_idealista="torrino",
        ricerca_casa="torrino",
        indirizzo_fallback="Roma - Torrino (EUR)",
    ),
    "torrino-mezzocammino": Zona(
        nome="torrino-mezzocammino",
        etichetta="Torrino Mezzocammino (EUR)",
        slug_immobiliare="torrino-mezzocammino-roma",
        slug_idealista="torrino-mezzocammino",
        ricerca_casa="torrino mezzocammino",
        indirizzo_fallback="Roma - Torrino Mezzocammino",
    ),
    "eur": Zona(
        nome="eur",
        etichetta="EUR (area circostante)",
        slug_immobiliare="eur-roma",
        slug_idealista="eur",
        ricerca_casa="eur",
        indirizzo_fallback="Roma - EUR",
    ),
    "montesacro": Zona(
        nome="montesacro",
        etichetta="Montesacro",
        slug_immobiliare="montesacro-roma",
        slug_idealista="montesacro",
        ricerca_casa="montesacro",
        indirizzo_fallback="Roma - Montesacro",
    ),
    "trieste": Zona(
        nome="trieste",
        etichetta="Trieste (quartiere Coppedè)",
        slug_immobiliare="trieste-roma",
        slug_idealista="trieste",
        ricerca_casa="trieste",
        indirizzo_fallback="Roma - Trieste",
    ),
}

ZONE_PREDEFINITA = "torrino"


def get_zona(nome: str) -> Zona:
    """Restituisce la zona richiesta o solleva un errore con i nomi validi."""
    chiave = nome.strip().lower()
    if chiave not in ZONE:
        raise KeyError(f"zona sconosciuta: {nome!r} (disponibili: {', '.join(sorted(ZONE))})")
    return ZONE[chiave]


@dataclass(frozen=True)
class CostiRistrutturazione:
    """Costo al mq per fascia di intervento."""

    leggera: int = 350    # tinteggiatura, piccoli interventi
    media: int = 700      # bagni, cucina, impianti parziali
    completa: int = 1100  # tutto da rifare (impianti + finiture)
    mq_di_riferimento: int = 75  # usata quando la scheda non dichiara i mq

    def per_livello(self, livello: str) -> int:
        if livello not in LIVELLI_RISTRUTTURAZIONE:
            raise ValueError(f"livello sconosciuto: {livello!r}")
        return getattr(self, livello)


@dataclass(frozen=True)
class Config:
    """Parametri della ricerca."""

    budget: int = 350_000
    locali_minimi: int = 3
    mq_minimi: int | None = None
    mq_ideale: int = 100
    margine_trattativa: float = 0.12
    zone: tuple[str, ...] = (ZONE_PREDEFINITA,)
    pagine_per_zona: int = 1
    solo_ristrutturare: bool = False
    richiedi_condizione: bool = False
    costi: CostiRistrutturazione = CostiRistrutturazione()
    livello_per_caso_peggiore: str = "media"
    timeout: int = 15
    tentativi: int = 3
    pausa: float = 1.5
    backoff: float = 1.0  # primo attesa fra i tentativi, poi raddoppia
    user_agent: str = USER_AGENT

    def __post_init__(self) -> None:
        if self.budget <= 0:
            raise ValueError("il budget deve essere positivo")
        if self.locali_minimi < 1:
            raise ValueError("i locali minimi devono essere almeno 1")
        try:
            for nome in self.zone:
                get_zona(nome)
        except KeyError as exc:
            raise ValueError(str(exc).strip("'")) from exc
        if self.livello_per_caso_peggiore not in LIVELLI_RISTRUTTURAZIONE:
            raise ValueError(
                f"livello_per_caso_peggiore deve essere uno di {LIVELLI_RISTRUTTURAZIONE}"
            )

    def con(self, **kwargs) -> Config:
        """Copia modificata della configurazione."""
        return replace(self, **kwargs)

    @property
    def prezzo_max_ricerca(self) -> int:
        """Tetto di ricerca: budget più il margine di trattativa."""
        return int(self.budget * (1 + self.margine_trattativa))

    @property
    def zone_risolte(self) -> tuple[Zona, ...]:
        return tuple(get_zona(z) for z in self.zone)

    @property
    def query_locali(self) -> str:
        """Elenco locali accettato dai portali a partire dal minimo richiesto.

        ``immobiliare.it`` usa ``6plus`` per "6 o più", gli altri usano l'elenco
        numerico: 3 locali minimi -> ``3,4,5,6,7,8,9,10``.
        """
        return ",".join(str(n) for n in range(self.locali_minimi, 11))

    def costo_ristrutturazione(self, mq: int | None, condizione: str) -> int:
        """Costo stimato di ristrutturazione per un annuncio.

        ``unknown`` costa 0 perché non abbiamo informazioni: il rischio viene
        segnalato nelle note invece di essere nascosto in un totale falsato.
        """
        if condizione == "ottimo":
            return 0
        if condizione == "parziale":
            livello = "leggera"
        elif condizione == "ristrutturare":
            livello = self.livello_per_caso_peggiore
        else:
            return 0
        superficie = mq or self.costi.mq_di_riferimento
        return superficie * self.costi.per_livello(livello)

    @property
    def prezzo_max_da_ristrutturare(self) -> int:
        """Prezzo massimo per un immobile da ristrutturare mantenendo il budget.

        Sostituisce il numero magico 270000 che compariva nei link di ricerca.
        """
        rientro = self.costi.mq_di_riferimento * self.costi.per_livello(
            self.livello_per_caso_peggiore
        )
        return max(self.budget - rientro, 0)
