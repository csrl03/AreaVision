"""
Fórmulas puras del dominio.

Sin efectos secundarios, sin I/O, sin dependencias de framework.
Estas funciones SON el sistema de medición. Mantenerlas idénticas
a la app Flutter garantiza resultados comparables entre plataformas.
"""
from __future__ import annotations

import math
from typing import Optional

from core.entities import MeasurementCategory
from core.constants import (
    CATEGORY_THRESHOLDS,
    CATEGORY_BOUNDARY_TOLERANCE,
    MIN_FACTOR_K,
    MAX_FACTOR_K,
    MIN_CALIBRATION_PIXELS,
)


def compute_factor_k(known_area_m2: float, area_pixels: float) -> float:
    """
    Calcula el FactorK base de calibración.

        factorK = área_real_m² / área_píxeles

    Args:
        known_area_m2: Área real del objeto de referencia en metros cuadrados.
        area_pixels:   Área del mismo objeto en píxeles cuadrados.

    Returns:
        FactorK (m² por px²).

    Raises:
        ValueError: Si algún argumento es <= 0.
    """
    if area_pixels <= 0:
        raise ValueError("El área en píxeles debe ser mayor que cero.")
    if known_area_m2 <= 0:
        raise ValueError("El área real conocida debe ser mayor que cero.")
    return known_area_m2 / area_pixels


def apply_distance_correction(
    factor_k_base: float,
    calibration_distance_cm: float,
    measurement_distance_cm: float,
) -> float:
    """
    Corrige el FactorK según la diferencia de distancia cámara-objeto.

    La proyección en perspectiva hace que el área aparente en píxeles
    sea proporcional al cuadrado de la distancia:

        factorK_corregido = factorK_base × (d_calibración / d_medición)²

    Si la distancia actual es igual a la de calibración, el factor no cambia.

    Args:
        factor_k_base:          FactorK calculado durante la calibración.
        calibration_distance_cm: Distancia cámara-objeto en la calibración (cm).
        measurement_distance_cm: Distancia cámara-objeto en la medición actual (cm).

    Raises:
        ValueError: Si alguna distancia es <= 0.
    """
    if calibration_distance_cm <= 0 or measurement_distance_cm <= 0:
        raise ValueError("Las distancias deben ser positivas (> 0 cm).")
    ratio = calibration_distance_cm / measurement_distance_cm
    return factor_k_base * (ratio ** 2)


def pixels_to_m2(area_pixels: float, factor_k: float) -> float:
    """
    Convierte área en píxeles a metros cuadrados.

        área_m² = área_píxeles × factorK

    Esta es la fórmula central del sistema, idéntica a la app Flutter.
    """
    return area_pixels * factor_k


def classify_area(area_m2: float) -> MeasurementCategory:
    """
    Asigna categoría A/B/C/D/error según el área en m².
    Itera en el orden definido en CATEGORY_THRESHOLDS;
    la primera ventana que contenga el valor gana.
    """
    for cat_name, (min_val, max_val) in CATEGORY_THRESHOLDS.items():
        if min_val <= area_m2 < max_val:
            return MeasurementCategory(cat_name)
    return MeasurementCategory.ERROR


def is_at_category_boundary(area_m2: float) -> bool:
    """
    Retorna True si el área está dentro del ±5% de un límite de categoría.
    Indica que un pequeño error de medición podría cambiar la categoría.
    """
    boundaries = [1.0, 2.0, 3.0, 4.0]
    for boundary in boundaries:
        if boundary > 0 and abs(area_m2 - boundary) / boundary <= CATEGORY_BOUNDARY_TOLERANCE:
            return True
    return False


def compute_circularity(area_pixels: float, perimeter_pixels: float) -> float:
    """
    Circularidad del contorno (1.0 = círculo perfecto, < 1 = formas irregulares).

        circularidad = 4π × área / perímetro²
    """
    if perimeter_pixels <= 0:
        return 0.0
    return (4 * math.pi * area_pixels) / (perimeter_pixels ** 2)


def validate_factor_k(factor_k: float) -> Optional[str]:
    """
    Valida que el FactorK esté en el rango admisible [MIN_FACTOR_K, MAX_FACTOR_K].

    Returns:
        Mensaje de error en español, o None si es válido.
    """
    if factor_k < MIN_FACTOR_K:
        return (
            f"FactorK demasiado pequeño ({factor_k:.2e}). "
            f"Mínimo permitido: {MIN_FACTOR_K:.2e}. "
            "El objeto de referencia es demasiado grande para la imagen."
        )
    if factor_k > MAX_FACTOR_K:
        return (
            f"FactorK demasiado grande ({factor_k:.2f}). "
            f"Máximo permitido: {MAX_FACTOR_K:.2f}. "
            "El objeto de referencia es demasiado pequeño en la imagen."
        )
    return None


def validate_calibration_pixels(area_pixels: float) -> Optional[str]:
    """
    Valida que el área de referencia sea lo suficientemente grande para ser precisa.

    Returns:
        Mensaje de error en español, o None si es válido.
    """
    if area_pixels < MIN_CALIBRATION_PIXELS:
        return (
            f"Área de referencia muy pequeña ({area_pixels:.0f} px²). "
            f"Mínimo recomendado: {MIN_CALIBRATION_PIXELS} px². "
            "Acerque más el objeto o use un objeto de referencia mayor."
        )
    return None
