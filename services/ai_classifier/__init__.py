"""
Módulo de clasificación IA — Feature Futura.

Estructura lista para conectar un modelo YOLOv8 entrenado con clases
personalizadas (Lámina, Tubo, Panel, etc.).
Actualmente el clasificador retorna None (sin clasificación activa).
"""
from services.ai_classifier.classifier_interface import ObjectClassifier, ClassificationResult
from services.ai_classifier.yolo_classifier import YOLOClassifier

__all__ = ["ObjectClassifier", "ClassificationResult", "YOLOClassifier"]
