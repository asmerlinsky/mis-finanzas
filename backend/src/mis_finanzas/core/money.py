"""Money helpers. Amounts are `Decimal` in memory and integer cents in the database."""

from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

CENT = Decimal("0.01")


def to_cents(amount: Decimal) -> int:
    """Convert an amount to integer cents, rounding half-even."""
    return int((amount.quantize(CENT, rounding=ROUND_HALF_EVEN) * 100).to_integral_value())


def from_cents(cents: int) -> Decimal:
    return (Decimal(cents) / 100).quantize(CENT)


def parse_amount(
    text: str, decimal_separator: str = ",", thousands_separator: str = "."
) -> Decimal:
    """Parse a localized amount such as `-1.234,56`, `$ 1.234,56` or `(1.234,56)`.

    Raises `ValueError` when the text is not a number.
    """
    cleaned = text.strip()
    for symbol in ("U$S", "USD", "$"):
        cleaned = cleaned.replace(symbol, "")
    cleaned = cleaned.strip()
    negative = cleaned.startswith("(") and cleaned.endswith(")")
    if negative:
        cleaned = cleaned[1:-1]
    cleaned = cleaned.replace(" ", "")
    if thousands_separator:
        cleaned = cleaned.replace(thousands_separator, "")
    cleaned = cleaned.replace(decimal_separator, ".")
    try:
        value = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError(f"not an amount: {text!r}") from exc
    if not value.is_finite():
        raise ValueError(f"not an amount: {text!r}")
    return -value if negative else value
