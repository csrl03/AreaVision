"""
Widget de feed de cámara en tiempo real con overlay de detección.

Usa QThread para leer y procesar frames sin bloquear la UI.
Emite señales con el frame procesado para que el QLabel lo muestre.
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QLabel, QWidget, QVBoxLayout, QSizePolicy

from core.entities import ProcessingResult, MeasurementCategory
from services.camera_service import CameraService
from services.measurement_service import MeasurementService

logger = logging.getLogger(__name__)


class CameraThread(QThread):
    """
    Thread de captura y procesamiento de frames.

    Señales:
        frame_ready(np.ndarray, ProcessingResult, float | None, MeasurementCategory | None)
        error_occurred(str)
    """
    frame_ready = pyqtSignal(object, object, object, object)
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        camera: CameraService,
        measurement_svc: MeasurementService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._camera = camera
        self._measurement_svc = measurement_svc
        self._running = False
        self._detection_enabled = True
        self._distance_cm: float = 50.0

    def set_distance(self, cm: float) -> None:
        self._distance_cm = max(1.0, cm)

    def set_detection_enabled(self, enabled: bool) -> None:
        self._detection_enabled = enabled

    def run(self) -> None:
        self._running = True
        logger.info("CameraThread iniciado")
        while self._running:
            try:
                frame = self._camera.read_frame()
                if self._detection_enabled:
                    result, area_m2, category = self._measurement_svc.process(
                        frame, self._distance_cm
                    )
                    self.frame_ready.emit(frame, result, area_m2, category)
                else:
                    self.frame_ready.emit(frame, None, None, None)
            except Exception as exc:
                logger.exception("Error en CameraThread")
                self.error_occurred.emit(str(exc))
                break
        logger.info("CameraThread detenido")

    def stop(self) -> None:
        self._running = False
        self.wait(3000)


def _ndarray_to_pixmap(frame_bgr: np.ndarray, target_size: QSize) -> QPixmap:
    """Convierte un frame BGR de OpenCV a QPixmap escalado al tamaño objetivo."""
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    qt_img = QImage(rgb.tobytes(), w, h, w * ch, QImage.Format.Format_RGB888)
    pixmap = QPixmap.fromImage(qt_img)
    return pixmap.scaled(
        target_size,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


class CameraFeedWidget(QLabel):
    """
    QLabel que muestra el feed de cámara en tiempo real con overlay de detección.

    Señales heredadas de QLabel; expone además:
        captured(np.ndarray, ProcessingResult, float | None, MeasurementCategory | None)
    """
    captured = pyqtSignal(object, object, object, object)

    def __init__(
        self,
        camera: CameraService,
        measurement_svc: MeasurementService,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._camera = camera
        self._thread: Optional[CameraThread] = None
        self._last_frame: Optional[np.ndarray] = None
        self._last_result: Optional[ProcessingResult] = None
        self._last_area_m2: Optional[float] = None
        self._last_category: Optional[MeasurementCategory] = None
        self._measurement_svc = measurement_svc

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(480, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setText("Sin señal de cámara")
        self.setStyleSheet("QLabel { color: #606070; font-size: 18px; }")

    # ─── Control del stream ───────────────────────────────────────────────────

    def start_stream(self) -> None:
        """Inicia el hilo de captura."""
        if self._thread and self._thread.isRunning():
            return
        self._thread = CameraThread(self._camera, self._measurement_svc, self)
        self._thread.frame_ready.connect(self._on_frame_ready)
        self._thread.error_occurred.connect(self._on_thread_error)
        self._thread.start()
        logger.info("Stream iniciado")

    def stop_stream(self) -> None:
        """Detiene el hilo de captura."""
        if self._thread:
            self._thread.stop()
            self._thread = None
        logger.info("Stream detenido")

    def set_detection_enabled(self, enabled: bool) -> None:
        if self._thread:
            self._thread.set_detection_enabled(enabled)

    def set_distance(self, cm: float) -> None:
        if self._thread:
            self._thread.set_distance(cm)

    def capture_current_frame(self) -> None:
        """Emite la señal 'captured' con el último frame procesado."""
        if self._last_frame is not None and self._last_result is not None:
            self.captured.emit(
                self._last_frame,
                self._last_result,
                self._last_area_m2,
                self._last_category,
            )

    # ─── Slots ────────────────────────────────────────────────────────────────

    def _on_frame_ready(
        self,
        frame: np.ndarray,
        result: Optional[ProcessingResult],
        area_m2: Optional[float],
        category: Optional[MeasurementCategory],
    ) -> None:
        self._last_frame = frame
        self._last_result = result
        self._last_area_m2 = area_m2
        self._last_category = category

        # Mostrar imagen con overlay si existe resultado, el frame crudo si no
        display = (
            result.contours_image
            if result is not None and result.contours_image is not None
            else frame
        )
        pixmap = _ndarray_to_pixmap(display, self.size())
        self.setPixmap(pixmap)

    def _on_thread_error(self, msg: str) -> None:
        self.setText(f"Error de cámara:\n{msg}")
        self.setPixmap(QPixmap())
