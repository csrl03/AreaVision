"""
Servicio de medición — Orquesta el flujo completo:
    frame → procesamiento OpenCV → calibración + corrección distancia
    → clasificación → compresión de silueta → persistencia.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional, Tuple

import numpy as np

from core.entities import (
    Measurement,
    MeasurementCategory,
    ProcessingResult,
    CalibrationData,
)
from core.exceptions import CalibrationNotFoundError
from core.formulas import pixels_to_m2, classify_area, is_at_category_boundary
from data.repositories import MeasurementRepository, ImageStorageService
from services.calibration_service import CalibrationService
from services.opencv_service import OpenCVService

logger = logging.getLogger(__name__)


class MeasurementService:
    """
    Orquesta el flujo completo de medición y persistencia.

    Dependencias inyectadas para facilitar pruebas y mantenimiento.
    """

    def __init__(
        self,
        opencv: OpenCVService,
        calibration: CalibrationService,
        repo: MeasurementRepository,
        image_storage: ImageStorageService,
    ) -> None:
        self._opencv = opencv
        self._calibration = calibration
        self._repo = repo
        self._image_storage = image_storage

    def process(
        self,
        frame: np.ndarray,
        distance_cm: float,
    ) -> Tuple[ProcessingResult, Optional[float], Optional[MeasurementCategory]]:
        """
        Procesa un frame y calcula el área en m² si hay calibración disponible.

        Returns:
            Tupla (processing_result, area_m2 | None, category | None).
            area_m2 y category son None cuando no hay calibración guardada.
        """
        area_m2: Optional[float] = None
        category: Optional[MeasurementCategory] = None

        if self._calibration.has_calibration():
            try:
                cal = self._calibration.load()
                corrected_fk = self._calibration.get_corrected_factor_k(cal, distance_cm)
                # Primer procesamiento sin overlay para obtener área_px
                result_raw = self._opencv.process_frame(frame, draw_overlay=False)
                if result_raw.success:
                    area_m2 = pixels_to_m2(result_raw.area_pixels, corrected_fk)
                    category = classify_area(area_m2)
            except CalibrationNotFoundError:
                pass
            except Exception as exc:
                logger.warning("Error aplicando calibración: %s", exc)

        # Segundo procesamiento con overlay enriquecido (área_m2 y categoría)
        result = self._opencv.process_frame(frame, draw_overlay=True, area_m2=area_m2, category=category)
        return result, area_m2, category

    def save_measurement(
        self,
        processing_result: ProcessingResult,
        area_m2: float,
        category: MeasurementCategory,
        distance_cm: float,
        name: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Measurement:
        """
        Guarda una medición con su imagen de silueta en la base de datos.

        Returns:
            Measurement con el ID asignado por la base de datos.

        Raises:
            CalibrationNotFoundError: Si ya no hay calibración (caso de borde).
        """
        cal = self._calibration.load()
        corrected_fk = self._calibration.get_corrected_factor_k(cal, distance_cm)
        timestamp = datetime.now()

        # Guardar imagen de silueta
        silhouette_path: Optional[str] = None
        if processing_result.contours_image is not None:
            try:
                silhouette_path = self._image_storage.save_silhouette(
                    processing_result.contours_image, timestamp
                )
            except Exception as exc:
                logger.warning("No se pudo guardar la silueta: %s", exc)

        measurement = Measurement(
            name=name or f"Medición {timestamp.strftime('%d/%m/%Y %H:%M')}",
            area_pixels=processing_result.area_pixels,
            area_m2=area_m2,
            category=category,
            factor_k_used=corrected_fk,
            distance_cm=distance_cm,
            timestamp=timestamp,
            notes=notes,
            silhouette_path=silhouette_path,
            perimeter_pixels=processing_result.perimeter_pixels,
            circularity=processing_result.circularity,
            confidence=self._compute_confidence(cal),
            is_valid=True,
        )
        measurement.id = self._repo.save(measurement)
        return measurement

    @staticmethod
    def _compute_confidence(calibration: CalibrationData) -> float:
        """Confianza degradada progresivamente si la calibración es antigua."""
        days = calibration.age_days
        if days < 7:
            return 1.0
        if days < 30:
            return 0.9
        if days < 60:
            return 0.7
        return 0.5
