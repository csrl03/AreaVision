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
from data.settings_repository import SettingsRepository, SENSITIVITY_PARAMS
from data.storage_repositories import (
    ScrapRepository,
    ShelfRepository,
    StorageAreaRepository,
)
from services.allocation_service import AllocationService
from services.cad_service import CadService
from services.camera_service import CameraService
from services.calibration_service import CalibrationService
from services.classification_service import ClassificationService, ReusePolicy
from services.measurement_service import MeasurementService
from services.opencv_service import OpenCVService
from services.ai_classifier import GeometryClassifier
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

    # Cargar configuración de usuario
    from config import DATA_DIR
    import os
    settings_repo = SettingsRepository(os.path.join(DATA_DIR, "settings.json"))
    cfg = settings_repo.load()

    # Construir servicios
    opencv_svc      = OpenCVService()

    # Aplicar configuración guardada al servicio de visión
    sens_params = SENSITIVITY_PARAMS.get(cfg.get("detection_sensitivity", "baja"), SENSITIVITY_PARAMS["baja"])
    close_k = max(11, sens_params["block_size"] // 3 | 1)
    opencv_svc.update_config(
        min_pixels=cfg.get("min_contour_area_pixels", 2000),
        adaptive_c=sens_params["adaptive_c"],
        block_size=sens_params["block_size"],
        close_kernel_size=close_k,
    )

    # Aplicar umbrales de categoría guardados
    from core.formulas import set_category_thresholds
    set_category_thresholds(cfg["category_thresholds"])
    calibration_svc = CalibrationService()
    repo            = MeasurementRepository(db)
    image_storage   = ImageStorageService()
    measurement_svc = MeasurementService(opencv_svc, calibration_svc, repo, image_storage)
    camera_svc      = CameraService()
    ai_classifier   = GeometryClassifier()

    # ── Gestión de retales (v2) ─────────────────────────────────────────────
    # La política se lee de settings.json y se pasa al servicio de
    # clasificación, de modo que las reglas de negocio viven en un solo sitio
    # y este archivo solo se ocupa de cablear dependencias.
    storage_repo  = StorageAreaRepository(db)
    shelf_repo    = ShelfRepository(db)
    scrap_repo    = ScrapRepository(db)
    classification_svc = ClassificationService(ReusePolicy.from_settings(cfg))
    allocation_svc = AllocationService(
        shelf_repo,
        scrap_repo,
        auto_recycle_sin_ubicacion=cfg.get("auto_recycle_sin_ubicacion", False),
    )
    cad_svc = CadService(
        simplify_ratio=cfg.get("dxf_simplify_epsilon_ratio", 0.02)
    )

    # Importar aquí para evitar importación circular antes de que los servicios existan
    from ui.windows.main_window import MainWindow

    window = MainWindow(
        camera_service=camera_svc,
        measurement_service=measurement_svc,
        calibration_service=calibration_svc,
        measurement_repo=repo,
        theme_manager=theme_manager,
        ai_classifier=ai_classifier,
        settings_repo=settings_repo,
        opencv_svc=opencv_svc,
        storage_repo=storage_repo,
        shelf_repo=shelf_repo,
        scrap_repo=scrap_repo,
        classification_service=classification_svc,
        allocation_service=allocation_svc,
        cad_service=cad_svc,
    )
    window.show()

    logger.info("UI lista — VisiSize %s", APP_VERSION)
    return app.exec()
