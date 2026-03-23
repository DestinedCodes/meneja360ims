from decimal import Decimal, InvalidOperation


def format_ksh(value):
    """Format a numeric value as Kenyan shillings with thousands separators."""
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        amount = Decimal("0")
    return f"KSh {amount:,.2f}"
