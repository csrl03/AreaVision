"""
Módulo de clasificación de objetos.

Clasificadores disponibles:
- GeometryClassifier  → contornos OpenCV, sin entrenamiento, disponible ahora
- YOLOClassifier      → YOLOv8 segmentación, requiere modelo .pt entrenado
"""
from services.ai_classifier.classifier_interface import ObjectClassifier, ClassificationResult
from services.ai_classifier.yolo_classifier import YOLOClassifier
from services.ai_classifier.geometry_classifier import GeometryClassifier

__all__ = ["ObjectClassifier", "ClassificationResult", "YOLOClassifier", "GeometryClassifier"]
