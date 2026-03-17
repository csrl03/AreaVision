"""
Interfaz abstracta para clasificadores de objetos.

TODOS los clasificadores futuros deben implementar esta interface
para ser intercambiables sin cambiar el resto del código.

Implementaciones previstas:
- YOLOClassifier     → YOLOv8 segmentación de instancias (Lámina, Tubo, Panel…)
- CustomCNNClassifier → CNN entrenada con imágenes propias del taller
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class ClassificationResult:
    """Resultado de clasificar el objeto principal en un frame."""
    object_class: str                                     # Ej: "Lámina", "Tubo", "Panel"
    confidence: float                                     # 0.0 – 1.0
    bounding_box: Optional[tuple[int, int, int, int]] = None  # (x, y, w, h) en píxeles
    model_name: str = "desconocido"

    @property
    def confidence_pct(self) -> str:
        return f"{self.confidence * 100:.1f}%"


class ObjectClassifier(ABC):
    """
    Interface abstracta para clasificadores de objetos en frames de cámara.

    Permite cambiar entre diferentes modelos de IA sin modificar
    la lógica de la UI ni del servicio de medición.
    """

    @abstractmethod
    def is_available(self) -> bool:
        """
        True si el clasificador está cargado y listo para inferencia.
        Retorna False si el modelo no está disponible (archivo no encontrado,
        dependencias no instaladas, etc.).
        """

    @abstractmethod
    def classify(self, frame: np.ndarray) -> Optional[ClassificationResult]:
        """
        Clasifica el objeto principal en el frame BGR.

        Args:
            frame: Frame BGR (numpy array H×W×3).

        Returns:
            ClassificationResult si se detectó un objeto con confianza suficiente,
            None si no hay detección o el clasificador no está disponible.
        """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Nombre identificador del modelo (para mostrar en la UI)."""
