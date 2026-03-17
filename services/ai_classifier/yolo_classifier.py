"""
Clasificador YOLOv8 — PLACEHOLDER (Feature Futura)
====================================================

Este módulo implementa ObjectClassifier usando YOLOv8 segmentación
de instancias (ultralytics). Actualmente retorna None (sin clasificación)
hasta que se entrene el modelo personalizado para las clases del taller.

─── Pasos para activar el clasificador ─────────────────────────────────────────

1. Recopilar dataset de imágenes de cada clase:
       Lámina, Tubo, Panel, Placa, Otro
   Formato recomendado: YOLO (anotaciones .txt con bounding boxes).

2. Entrenar el modelo:
       from ultralytics import YOLO
       model = YOLO("yolov8n-seg.pt")   # nano-seg como base
       model.train(data="dataset.yaml", epochs=100, imgsz=640)

3. Guardar el modelo entrenado en:
       AreaCamPython_v1/data/models/visisize_classifier.pt

4. Descomentar el bloque "ACTIVAR MODELO" en __init__ y en classify().

5. Reiniciar la aplicación — el clasificador se cargará automáticamente.

─── Dependencia ya instalada ────────────────────────────────────────────────────
    ultralytics está en requirements.txt. No se necesita ninguna instalación extra.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import numpy as np

from services.ai_classifier.classifier_interface import ObjectClassifier, ClassificationResult

logger = logging.getLogger(__name__)

_MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "models", "visisize_classifier.pt"
)

# Clases objetivo del clasificador (deben coincidir con dataset.yaml)
TARGET_CLASSES: list[str] = [
    "Lámina",
    "Tubo",
    "Panel",
    "Placa",
    "Otro",
]

# Umbral mínimo de confianza para reportar una detección
CONFIDENCE_THRESHOLD: float = 0.50


class YOLOClassifier(ObjectClassifier):
    """
    Clasificador basado en YOLOv8 segmentación de instancias.
    Retorna None hasta que el modelo esté entrenado y disponible.
    """

    def __init__(self) -> None:
        self._model = None
        self._available = False

        # ── ACTIVAR MODELO ── (descomentar cuando el .pt esté listo)
        # if os.path.exists(_MODEL_PATH):
        #     try:
        #         from ultralytics import YOLO
        #         self._model = YOLO(_MODEL_PATH)
        #         self._available = True
        #         logger.info("Modelo YOLOv8 cargado: %s", _MODEL_PATH)
        #     except Exception as exc:
        #         logger.warning("No se pudo cargar el modelo YOLO: %s", exc)
        # else:
        #     logger.info("Modelo YOLOv8 no encontrado en: %s", _MODEL_PATH)

    def is_available(self) -> bool:
        return self._available

    def classify(self, frame: np.ndarray) -> Optional[ClassificationResult]:
        """
        [PLACEHOLDER] Siempre retorna None.

        Cuando el modelo esté disponible, este método ejecutará la inferencia
        YOLOv8 y retornará la clase con mayor confianza.
        """
        if not self._available or self._model is None:
            return None

        # ── INFERENCIA YOLO ── (descomentar cuando el modelo esté listo)
        # try:
        #     results = self._model(frame, verbose=False, conf=CONFIDENCE_THRESHOLD)
        #     if results and results[0].boxes is not None and len(results[0].boxes):
        #         best_box = results[0].boxes[0]
        #         cls_id   = int(best_box.cls[0])
        #         conf     = float(best_box.conf[0])
        #         x, y, w, h = best_box.xywh[0].int().tolist()
        #         cls_name = (
        #             TARGET_CLASSES[cls_id] if cls_id < len(TARGET_CLASSES) else "Otro"
        #         )
        #         return ClassificationResult(
        #             object_class=cls_name,
        #             confidence=conf,
        #             bounding_box=(x, y, w, h),
        #             model_name=self.model_name,
        #         )
        # except Exception as exc:
        #     logger.warning("Error en inferencia YOLO: %s", exc)
        return None

    @property
    def model_name(self) -> str:
        return "YOLOv8-seg — pendiente de entrenamiento"
