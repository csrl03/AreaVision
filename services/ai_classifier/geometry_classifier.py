"""
Clasificador geométrico — sin entrenamiento, 100% OpenCV
=========================================================

Clasifica el objeto principal de un frame analizando su **contorno más grande**
con tres métricas geométricas clásicas:

    Circularidad  = 4π·Área / Perímetro²        (1.0 = círculo perfecto)
    Relación aspecto = lado_largo / lado_corto  (del rectángulo mínimo rotado)
    Extensión     = Área_contorno / Área_bbox   (qué tan "llena" está la bbox)

Lógica de clasificación
-----------------------
Vista frontal de tubo (sección circular):
    → Circularidad > 0.72

Vista lateral de tubo (rectángulo muy alargado con extremos redondeados):
    → Aspecto ≥ 3.5  Y  extensión > 0.70

Lámina (plano rectangular, relación media):
    → Aspecto en [1.4, 3.5)  Y  extensión > 0.78

Placa (cuadrada o casi cuadrada):
    → Aspecto en [1.0, 1.4)  Y  extensión > 0.82

Panel (muy plano/alargado similar a lámina pero más largo):
    → Aspecto ≥ 3.5  Y  extensión > 0.85  (extremos rectos, no redondeados)

En cualquier otro caso → "Otro"

Uso inmediato
-------------
    from services.ai_classifier import GeometryClassifier
    clf = GeometryClassifier()
    result = clf.classify(frame)          # frame = np.ndarray BGR de OpenCV
    if result:
        print(result.object_class, result.confidence_pct)
"""
from __future__ import annotations

import logging
import math
from typing import Optional

import cv2
import numpy as np

from services.ai_classifier.classifier_interface import ObjectClassifier, ClassificationResult

logger = logging.getLogger(__name__)

# ── Umbrales ajustables ────────────────────────────────────────────────────────
_CIRCULARITY_TUBE_END   = 0.72   # sección circular → Tubo (vista frontal)
_ASPECT_ELONGATED       = 3.5    # muy alargado
_ASPECT_LAMINA_MIN      = 1.4    # inicio zona "lámina"
_EXTENT_TUBE_SIDE       = 0.70   # extensión mínima para tubo lateral
_EXTENT_LAMINA          = 0.78   # extensión mínima para lámina
_EXTENT_PLACA           = 0.82   # extensión mínima para placa
_EXTENT_PANEL           = 0.85   # extensión alta + muy alargado → panel recto
_MIN_CONTOUR_AREA_PX    = 500    # contornos más pequeños se ignoran (ruido)
# ──────────────────────────────────────────────────────────────────────────────


def _compute_metrics(contour) -> tuple[float, float, float]:
    """Devuelve (circularidad, relacion_aspecto, extension) del contorno."""
    area = cv2.contourArea(contour)
    if area < 1:
        return 0.0, 1.0, 0.0

    perimeter = cv2.arcLength(contour, closed=True)
    circularity = (4 * math.pi * area / (perimeter ** 2)) if perimeter > 0 else 0.0

    # Rectángulo mínimo rotado — agnóstico a la orientación
    _, (w, h), _ = cv2.minAreaRect(contour)
    if min(w, h) < 1:
        aspect_ratio = 1.0
    else:
        aspect_ratio = max(w, h) / min(w, h)

    # Extensión: área contorno / área bbox alineada con ejes
    bx, by, bw, bh = cv2.boundingRect(contour)
    bbox_area = bw * bh
    extent = area / bbox_area if bbox_area > 0 else 0.0

    return circularity, aspect_ratio, extent


def _classify_metrics(circ: float, aspect: float, extent: float) -> tuple[str, float]:
    """
    Reglas heurísticas → (clase, confianza_aprox).
    La confianza se estima por qué tan "centrado" está cada métrica en su zona.
    """
    # ── 1. Tubo sección circular ───────────────────────────────────────────────
    if circ >= _CIRCULARITY_TUBE_END:
        confidence = min(1.0, circ / 1.0)          # más cercano a 1 = más confianza
        return "Tubo", round(confidence, 3)

    # ── 2. Panel recto muy alargado (extremos planos, extensión alta) ──────────
    if aspect >= _ASPECT_ELONGATED and extent >= _EXTENT_PANEL:
        confidence = min(1.0, 0.60 + (extent - _EXTENT_PANEL) * 4)
        return "Panel", round(confidence, 3)

    # ── 3. Tubo lateral (extremos redondeados → extensión media-baja) ─────────
    if aspect >= _ASPECT_ELONGATED and extent >= _EXTENT_TUBE_SIDE:
        confidence = min(1.0, 0.55 + (1.0 - extent) * 1.5)
        return "Tubo", round(confidence, 3)

    # ── 4. Lámina (rectangular medio) ─────────────────────────────────────────
    if _ASPECT_LAMINA_MIN <= aspect < _ASPECT_ELONGATED and extent >= _EXTENT_LAMINA:
        confidence = min(1.0, 0.55 + extent * 0.5)
        return "Lámina", round(confidence, 3)

    # ── 5. Placa (casi cuadrada) ───────────────────────────────────────────────
    if aspect < _ASPECT_LAMINA_MIN and extent >= _EXTENT_PLACA:
        confidence = min(1.0, 0.50 + extent * 0.5)
        return "Placa", round(confidence, 3)

    return "Otro", 0.40


class GeometryClassifier(ObjectClassifier):
    """
    Clasificador basado en análisis de contornos OpenCV.
    Siempre disponible — no requiere modelos ni datos de entrenamiento.

    Clases producidas: Tubo | Lámina | Panel | Placa | Otro
    """

    # ── ObjectClassifier interface ────────────────────────────────────────────

    def is_available(self) -> bool:
        return True  # Solo depende de OpenCV, que ya es requerimiento del proyecto

    def classify(self, frame: np.ndarray) -> Optional[ClassificationResult]:
        """
        Analiza el contorno más grande del frame y devuelve su clasificación.

        Parámetros
        ----------
        frame : np.ndarray
            Imagen BGR (uint8) tal como llega de OpenCV.

        Retorna
        -------
        ClassificationResult o None si no se detecta ningún contorno útil.
        """
        try:
            contour, bbox = self._find_main_contour(frame)
            if contour is None:
                return None

            circ, aspect, extent = _compute_metrics(contour)
            object_class, confidence = _classify_metrics(circ, aspect, extent)

            logger.debug(
                "GeometryClassifier | circ=%.3f  aspect=%.2f  extent=%.3f → %s (%.0f%%)",
                circ, aspect, extent, object_class, confidence * 100,
            )

            return ClassificationResult(
                object_class=object_class,
                confidence=confidence,
                bounding_box=bbox,
                model_name=self.model_name,
            )

        except Exception as exc:
            logger.warning("GeometryClassifier error: %s", exc)
            return None

    def classify_from_result(self, result) -> Optional[ClassificationResult]:
        """
        Clasifica usando las métricas ya calculadas por OpenCVService (ProcessingResult).

        Es más fiable que classify(frame) porque reutiliza el contorno que OpenCV
        ya detectó con los parámetros de sensibilidad del usuario.

        Parámetros
        ----------
        result : ProcessingResult
            Resultado del pipeline OpenCVService (circularity, aspect_ratio, bounding_box,
            area_pixels ya calculados).

        Retorna
        -------
        ClassificationResult o None si el resultado no tiene contorno válido.
        """
        try:
            if result is None or not result.success:
                return None

            x, y, w, h = result.bounding_box
            bbox_area = w * h
            extent = result.area_pixels / bbox_area if bbox_area > 0 else 0.0

            object_class, confidence = _classify_metrics(
                result.circularity, result.aspect_ratio, extent
            )

            logger.debug(
                "classify_from_result | circ=%.3f  aspect=%.2f  extent=%.3f → %s (%.0f%%)",
                result.circularity, result.aspect_ratio, extent,
                object_class, confidence * 100,
            )

            return ClassificationResult(
                object_class=object_class,
                confidence=confidence,
                bounding_box=result.bounding_box,
                model_name=self.model_name,
            )
        except Exception as exc:
            logger.warning("classify_from_result error: %s", exc)
            return None

    @property
    def model_name(self) -> str:
        return "GeometryClassifier (contornos OpenCV)"

    # ── Helpers privados ──────────────────────────────────────────────────────

    def _find_main_contour(
        self, frame: np.ndarray
    ) -> tuple[Optional[np.ndarray], Optional[tuple[int, int, int, int]]]:
        """
        Pre-procesa el frame y devuelve el contorno de mayor área junto
        con su bounding box (x, y, w, h).
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Desenfoque para reducir ruido de textura
        blurred = cv2.GaussianBlur(gray, (7, 7), 0)

        # Umbralización adaptativa: funciona con distintas iluminaciones
        binary = cv2.adaptiveThreshold(
            blurred, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV,
            blockSize=31,
            C=6,
        )

        # Operaciones morfológicas para cerrar huecos pequeños
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=2)

        contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None, None

        # Seleccionar el contorno más grande (objeto principal)
        main = max(contours, key=cv2.contourArea)
        if cv2.contourArea(main) < _MIN_CONTOUR_AREA_PX:
            return None, None

        x, y, w, h = cv2.boundingRect(main)
        return main, (x, y, w, h)
