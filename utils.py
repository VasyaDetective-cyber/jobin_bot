"""Дрібні допоміжні функції."""


def fmt(price) -> str:
    """1490 -> '1 490'; 350.5 -> '350.50'."""
    value = float(price)
    if value == int(value):
        return f"{int(value):,}".replace(",", " ")
    return f"{value:.2f}"
