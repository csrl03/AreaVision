"""
Entidades del dominio — Clases de datos puras sin dependencias externas ni de UI.
Equivalente a las entities de la app Flutter.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class MeasurementCategory(Enum):
    """
    Clasificación de área medida.
    Compatible con MeasurementCategory de la app Flutter (mismos valores y rangos).
    """
    A = "A"          # < 1.0 m²  — verde
    B = "B"          # 1.0–2.0 m² — azul
    C = "C"          # 2.0–3.0 m² — ámbar
    D = "D"          # 3.0–4.0 m² — naranja
    ERROR = "error"  # ≥ 4.0 m²  — rojo

    @property
    def label_es(self) -> str:
        return {
            MeasurementCategory.A:     "A — Pequeño  (< 1 m²)",
            MeasurementCategory.B:     "B — Mediano  (1–2 m²)",
            MeasurementCategory.C:     "C — Grande   (2–3 m²)",
            MeasurementCategory.D:     "D — Muy grande (3–4 m²)",
            MeasurementCategory.ERROR: "Fuera de rango (> 4 m²)",
        }[self]

    @property
    def hex_color(self) -> str:
        return {
            MeasurementCategory.A:     "#4caf50",
            MeasurementCategory.B:     "#2196f3",
            MeasurementCategory.C:     "#ff9800",
            MeasurementCategory.D:     "#ff5722",
            MeasurementCategory.ERROR: "#f44336",
        }[self]


@dataclass
class CalibrationData:
    """
    Datos de calibración almacenados.
    El campo clave es `factor_k`: metros cuadrados por píxel en el instante de calibración.
    """
    factor_k: float                     # m²/px² al momento de calibrar
    calibration_area_pixels: float      # Área del objeto de referencia en px²
    calibration_area_real_m2: float     # Área real conocida del objeto de referencia (m²)
    calibration_image_width: int        # Resolución de la imagen usada en la calibración
    calibration_image_height: int
    calibration_distance_cm: float      # Distancia cámara-objeto durante la calibración (cm)
    calibration_date: datetime          # Fecha y hora de la calibración
    notes: Optional[str] = None

    @property
    def is_recent(self) -> bool:
        """True si la calibración tiene menos de 30 días."""
        from core.constants import CALIBRATION_MAX_AGE_DAYS
        return (datetime.now() - self.calibration_date).days < CALIBRATION_MAX_AGE_DAYS

    @property
    def age_days(self) -> int:
        return (datetime.now() - self.calibration_date).days

    def is_valid_for_resolution(self, width: int, height: int) -> bool:
        """True si la resolución actual está dentro del ±10% de la resolución de calibración."""
        from core.constants import CALIBRATION_RESOLUTION_TOLERANCE
        tol = CALIBRATION_RESOLUTION_TOLERANCE
        w_ok = abs(width - self.calibration_image_width) / max(self.calibration_image_width, 1) <= tol
        h_ok = abs(height - self.calibration_image_height) / max(self.calibration_image_height, 1) <= tol
        return w_ok and h_ok


@dataclass
class ProcessingResult:
    """Resultado del pipeline OpenCV para un frame."""
    area_pixels: float
    perimeter_pixels: float
    contour_count: int
    circularity: float
    aspect_ratio: float
    image_width: int
    image_height: int
    bounding_box: tuple[int, int, int, int]  # (x, y, w, h)
    processing_time_ms: float
    # Imágenes intermedias para visualización (numpy arrays BGR o None)
    original_frame: Optional[Any] = None
    grayscale_image: Optional[Any] = None
    binary_image: Optional[Any] = None
    contours_image: Optional[Any] = None
    error_message: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error_message is None and self.area_pixels > 0


@dataclass
class Measurement:
    """Registro de medición persistido en la base de datos."""
    area_pixels: float
    area_m2: float
    category: MeasurementCategory
    factor_k_used: float
    distance_cm: float
    timestamp: datetime
    id: Optional[int] = None
    name: Optional[str] = None
    notes: Optional[str] = None
    silhouette_path: Optional[str] = None
    perimeter_pixels: Optional[float] = None
    circularity: Optional[float] = None
    confidence: Optional[float] = None
    is_valid: bool = True

    @property
    def area_cm2(self) -> float:
        return self.area_m2 * 10_000

    @property
    def display_name(self) -> str:
        return self.name or f"Medición {self.timestamp.strftime('%d/%m/%Y %H:%M')}"
