"""
Valoración económica del material.

Una única variable configurable: `costo_por_m2_lamina` (precio de la lámina nueva).

    valor_estimado = area_m2 × costo_por_m2_lamina

El precio del material reciclado (scrap) suele ser una fracción del precio de la
lámina nueva, pero esa relación depende del mercado y de la loginera. Aquí
**no** se asume: `ScrapDestination.RECICLABLE` no multiplica por ningún factor.
Si el negocio necesita valuing el chatarra, se añade un `precio_reciclaje` como
campo independiente, nunca como un factor oculto sobre el mismo número.
"""
from __future__ import annotations

from typing import Optional

DEFAULT_CURRENCY_CODE: str = "COP"
DEFAULT_CURRENCY_SYMBOL: str = "$"
DEFAULT_COST_PER_M2: float = 0.0


def compute_estimated_value(area_m2: float, cost_per_m2: float) -> float:
    """
    Calcula el valor estimado de un retal.

    Args:
        area_m2:      Área del retal en m².
        cost_per_m2: Costo por m² de lámina.

    Returns:
        Valor estimado. 0.0 si el costo no está configurado o el área es inválida
        (un 0 es preferible a un None: la UI siempre tiene algo que mostrar).
    """
    if area_m2 <= 0 or cost_per_m2 <= 0:
        return 0.0
    return area_m2 * cost_per_m2


def format_currency(
    value: Optional[float],
    symbol: str = DEFAULT_CURRENCY_SYMBOL,
    decimals: int = 0,
) -> str:
    """
    Formatea un valor monetario.

    COP no tiene decimales en la práctica, así que por defecto se redondea al
    entero y se usa separador de miles es-EC (punto cada 3 dígitos).

        >>> format_currency(119000.0)
        '$ 119.000'
        >>> format_currency(0.0)
        'Sin costo configurado'
    """
    if value is None or value <= 0:
        return "Sin costo configurado"
    rounded = round(value)
    return f"{symbol} {rounded:,}".replace(",", ".")
