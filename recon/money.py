"""Money helpers. All amounts are Decimal. Never use float for money."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0")


def parse_amount(value) -> Decimal:
    """Parse text into a finite Decimal. Raises ValueError for empty or non-numeric text."""
    text = str(value).strip().replace(",", "")
    if text == "":
        raise ValueError("empty amount")
    try:
        number = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"non-numeric amount '{value}'")
    if not number.is_finite():
        raise ValueError(f"non-finite amount '{value}'")
    return number


def round_half_up(value: Decimal) -> Decimal:
    """Round to 2 decimals, halves go away from zero. This is the bank rounding rule we assume."""
    return value.quantize(CENT, rounding=ROUND_HALF_UP)
