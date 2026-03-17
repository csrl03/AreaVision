"""
Servicio de calibración.

Calcula el FactorK (m²/px²), aplica la corrección cuadrática por distancia,
valida los datos y los persiste en un archivo JSON local.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Optional

from config import CALIBRATION_PATH
from core.entities import CalibrationData
from core.exceptions import CalibrationNotFoundError, CalibrationValidationError
from core.formulas import (
    compute_factor_k,
    apply_distance_correction,
    validate_factor_k,
    validate_calibration_pixels,
)

logger = logging.getLogger(__name__)


class CalibrationService:
    """
    Gestiona el FactorK: cálculo, corrección por distancia,
    validación de datos y persistencia en JSON local.
    """

    # ─── Cálculo ────────────────────────────────────────────────────────────────

    def calculate(
        self,
        area_pixels: float,
        known_area_m2: float,
        image_width: int,
        image_height: int,
        distance_cm: float,
        notes: Optional[str] = None,
    ) -> CalibrationData:
        """
        Calcula el FactorK a partir de un área de referencia conocida.

        Valida que el área en píxeles sea suficiente y que el FactorK resultante
        esté en el rango admisible antes de retornar.

        Raises:
            CalibrationValidationError: Si los datos no son válidos.
        """
        error = validate_calibration_pixels(area_pixels)
        if error:
            raise CalibrationValidationError(error)

        if distance_cm <= 0:
            raise CalibrationValidationError(
                "La distancia debe ser mayor que cero."
            )

        fk = compute_factor_k(known_area_m2, area_pixels)
        error = validate_factor_k(fk)
        if error:
            raise CalibrationValidationError(error)

        cal = CalibrationData(
            factor_k=fk,
            calibration_area_pixels=area_pixels,
            calibration_area_real_m2=known_area_m2,
            calibration_image_width=image_width,
            calibration_image_height=image_height,
            calibration_distance_cm=distance_cm,
            calibration_date=datetime.now(),
            notes=notes,
        )
        logger.info(
            "Calibración calculada: factorK=%.4e, distancia=%.1f cm", fk, distance_cm
        )
        return cal

    def get_corrected_factor_k(
        self,
        calibration: CalibrationData,
        current_distance_cm: float,
    ) -> float:
        """
        Retorna el FactorK ajustado por la distancia actual.

        Si la distancia es igual a la de calibración el resultado es idéntico al base.
        Si el objeto está más lejos, el FactorK aumenta (los objetos parecen más pequeños).
        """
        return apply_distance_correction(
            calibration.factor_k,
            calibration.calibration_distance_cm,
            current_distance_cm,
        )

    # ─── Persistencia ───────────────────────────────────────────────────────────

    def save(self, calibration: CalibrationData) -> None:
        """Guarda la calibración en el archivo JSON local. Sobreescribe la anterior."""
        data = {
            "factor_k": calibration.factor_k,
            "calibration_area_pixels": calibration.calibration_area_pixels,
            "calibration_area_real_m2": calibration.calibration_area_real_m2,
            "calibration_image_width": calibration.calibration_image_width,
            "calibration_image_height": calibration.calibration_image_height,
            "calibration_distance_cm": calibration.calibration_distance_cm,
            "calibration_date": calibration.calibration_date.isoformat(),
            "notes": calibration.notes,
        }
        os.makedirs(os.path.dirname(CALIBRATION_PATH), exist_ok=True)
        with open(CALIBRATION_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(
            "Calibración guardada: factorK=%.4e, distancia=%.1f cm",
            calibration.factor_k,
            calibration.calibration_distance_cm,
        )

    def load(self) -> CalibrationData:
        """
        Carga la calibración guardada.

        Raises:
            CalibrationNotFoundError: Si no hay archivo de calibración.
            CalibrationValidationError: Si el archivo está corrupto.
        """
        if not self.has_calibration():
            raise CalibrationNotFoundError(
                "No hay calibración guardada. "
                "Vaya a Configuración → Nueva calibración."
            )
        try:
            with open(CALIBRATION_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as exc:
            raise CalibrationValidationError(
                f"El archivo de calibración está dañado: {exc}"
            ) from exc

        return CalibrationData(
            factor_k=float(data["factor_k"]),
            calibration_area_pixels=float(data["calibration_area_pixels"]),
            calibration_area_real_m2=float(data["calibration_area_real_m2"]),
            calibration_image_width=int(data["calibration_image_width"]),
            calibration_image_height=int(data["calibration_image_height"]),
            calibration_distance_cm=float(data["calibration_distance_cm"]),
            calibration_date=datetime.fromisoformat(data["calibration_date"]),
            notes=data.get("notes"),
        )

    def has_calibration(self) -> bool:
        """Retorna True si existe un archivo de calibración guardado."""
        return os.path.exists(CALIBRATION_PATH)
