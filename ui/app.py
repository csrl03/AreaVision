"""
Punto de entrada de la UI — Inicializa QApplication y construye el grafo de dependencias.
"""
from __future__ import annotations

import logging
import sys

from PyQt6.QtWidgets import QApplication

from config import APP_TITLE, APP_VERSION, DEFAULT_THEME
from data.database import DatabaseManager
from data.repositories import MeasurementRepository, ImageStorageService
from services.camera_service import CameraService
from services.calibration_service import CalibrationService
from services.measurement_service import MeasurementService
from services.opencv_service import OpenCVService
from services.ai_classifier import YOLOClassifier
from ui.theme import ThemeManager

logger = logging.getLogger(__name__)


def run_app(db: DatabaseManager) -> int:
    """
    Construye el grafo de dependencias, crea la ventana principal y ejecuta el loop de UI.

    Returns:
        Código de salida del proceso.
    """
    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    app.setApplicationVersion(APP_VERSION)

    # Cargar tema
    theme_manager = ThemeManager()
    theme_manager.apply(app, DEFAULT_THEME)

    # Construir servicios
    opencv_svc      = OpenCVService()
    calibration_svc = CalibrationService()
    repo            = MeasurementRepository(db)
    image_storage   = ImageStorageService()
    measurement_svc = MeasurementService(opencv_svc, calibration_svc, repo, image_storage)
    camera_svc      = CameraService()
    ai_classifier   = YOLOClassifier()

    # Importar aquí para evitar importación circular antes de que los servicios existan
    from ui.windows.main_window import MainWindow

    window = MainWindow(
        camera_service=camera_svc,
        measurement_service=measurement_svc,
        calibration_service=calibration_svc,
        measurement_repo=repo,
        theme_manager=theme_manager,
        ai_classifier=ai_classifier,
    )
    window.show()

    logger.info("UI lista — VisiSize %s", APP_VERSION)
    return app.exec()
