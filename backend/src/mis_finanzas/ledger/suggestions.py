"""Rule suggestions: group uncategorized movements by merchant, from their normalized text.

Pure functions; `reports/rule_suggestions.py` feeds them the ledger's movements.

- `merchant_key`: the stable part of a description. It drops the bank's own type prefixes
  (`COMPRA CON TARJETA DE DEBITO`) and card references (`TARJ NRO.`), words with digits
  (vouchers, card numbers, codes), one-letter words and installments, and keeps the first
  `KEY_WORDS` words left.
- `pattern_for`: the text a `contiene` rule needs to catch a group. Rules match the normalized
  text literally, so the pattern is the key as printed (`PAYU/AR/UBER`), not the key itself
  (`PAYU AR UBER`).
"""

import re
from collections import Counter
from collections.abc import Hashable, Sequence
from dataclasses import dataclass, field

KEY_WORDS = 3
# The bank's own wording for a movement's type, ahead of the merchant. Not personal data.
TYPE_PREFIXES = (
    "COMPRA CON TARJETA DE DEBITO",
    "PAGO DE SERVICIOS",
    "DEBITO AUTOMATICO",
    "TRANSFERENCIA NO GRAVADA",
    "TRANSF. NO GRAVADA",
    "TRANSFERENCIA RECIBIDA DE",
    "TRANSFERENCIA RECIBIDA",
)
# Bank wording inside descriptions: the debit card reference (`TARJ NRO. 1234`).
NOISE_WORDS = frozenset({"TARJ", "NRO"})
_TOKEN = re.compile(r"[^\s/*]+")
_PUNCTUATION = ".,;:-_()[]|'\"#"


@dataclass(frozen=True)
class _Token:
    word: str  # cleaned, "" when it doesn't count toward a key
    start: int
    end: int


def _clean(word: str) -> str:
    word = word.strip(_PUNCTUATION)
    if len(word) <= 1 or word in NOISE_WORDS or any(ch.isdigit() for ch in word):
        return ""
    return word


def _tokens(text: str) -> list[_Token]:
    """The text's words after its type prefix, with their place in the text."""
    start = next((len(p) for p in TYPE_PREFIXES if text.startswith(p)), 0)
    return [
        _Token(_clean(m.group()), m.start(), m.end())
        for m in _TOKEN.finditer(text)
        if m.start() >= start
    ]


def merchant_key(description_norm: str) -> str | None:
    """`PAYU/AR/UBER 1234` -> `PAYU AR UBER`; None when no word is left."""
    words = [token.word for token in _tokens(description_norm) if token.word]
    return " ".join(words[:KEY_WORDS]) or None


def _span(description_norm: str, key: str) -> str | None:
    """The text from the key's first word through the key words that follow it directly.

    A word with digits between two key words ends the span: it varies from one movement to
    the next, so a pattern holding it would miss the others.
    """
    words = key.split()
    tokens = _tokens(description_norm)
    first = next((i for i, t in enumerate(tokens) if t.word == words[0]), None)
    if first is None:
        return None
    last = first
    while (
        last + 1 < len(tokens)
        and last + 1 - first < len(words)
        and tokens[last + 1].word == words[last + 1 - first]
    ):
        last += 1
    return description_norm[tokens[first].start : tokens[last].end]


def pattern_for(descriptions: Sequence[str], key: str) -> str:
    """The most frequent way the group's descriptions print the key."""
    spans = [s for s in (_span(d, key) for d in descriptions) if s]
    return Counter(spans).most_common(1)[0][0] if spans else key.split()[0]


@dataclass
class Group[T, K: Hashable]:
    key: str
    extra: K  # what else groups apart: the sign
    items: list[T] = field(default_factory=list)


def group[T, K: Hashable](items: Sequence[tuple[str, K, T]]) -> list[Group[T, K]]:
    """`items` are (description_norm, extra, item); grouped by (merchant key, extra)."""
    found: dict[tuple[str, K], Group[T, K]] = {}
    for description, extra, item in items:
        key = merchant_key(description)
        if key is not None:
            found.setdefault((key, extra), Group(key, extra)).items.append(item)
    return list(found.values())
