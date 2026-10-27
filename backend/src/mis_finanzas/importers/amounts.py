"""Signed amounts as statements print them: `-$ 1.234,56`, `$-533.444,86`, `U$S47,11`."""

import re
from dataclasses import dataclass
from decimal import Decimal

from mis_finanzas.core.money import parse_amount

# Longest symbols first, so `U$S` isn't read as `$`.
CURRENCY_SYMBOLS = (("U$S", "USD"), ("USD", "USD"), ("$", "ARS"))
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str | None  # "ARS", "USD", or None when no symbol was printed


def _split_symbol(text: str) -> tuple[str, str | None]:
    for symbol, currency in CURRENCY_SYMBOLS:
        if symbol in text:
            return text.replace(symbol, "", 1), currency
    return text, None


def parse_money(text: str, decimal_separator: str = ",", thousands_separator: str = ".") -> Money:
    """Raises `ValueError` when the text holds no amount.

    The minus sign may come before or after the symbol (`-$ 5,00`, `$-5,00`, `-U$S 5,00`);
    parentheses also mean negative (`(5,00)`).
    """
    compact = _SPACES.sub("", text)
    rest, currency = _split_symbol(compact)
    negative = rest.startswith("-")
    number = parse_amount(rest.lstrip("-"), decimal_separator, thousands_separator)
    return Money(amount=-abs(number) if negative or number < 0 else number, currency=currency)


# An amount with its currency symbol, as summary lines print it: `$ 924.940,36`, `-U$S 47,52`.
_MONEY_IN_TEXT = re.compile(r"-?\s*(?:U\$S|\$)\s*-?\s*\d[\d.]*,\d{2}")


def money_in_text(text: str) -> list[Money]:
    """Every symbol-marked amount in a line, left to right (`Total a pagar $ 1,00 U$S 2,00`)."""
    return [parse_money(match.group()) for match in _MONEY_IN_TEXT.finditer(text)]
