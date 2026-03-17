"""
Widget de selección de área por rectángulo.

El usuario dibuja un rectángulo sobre una imagen congelada.
El widget escala las coordenadas del widget al tamaño real de la imagen
para calcular el área en píxeles reales.
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QPoint, QRect, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap, QPainter, QPen, QColor, QFont
from PyQt6.QtWidgets import QLabel, QSizePolicy, QWidget

logger = logging.getLogger(__name__)


class AreaSelectorWidget(QLabel):
    """
    Muestra una imagen congelada y permite al usuario dibujar un rectángulo
    para seleccionar el área del objeto de referencia.

    Señal:
        area_selected(area_pixels: float, rect_widget: QRect)
            Emitida cuando el usuario suelta el ratón tras dibujar el rectángulo.
    """
    area_selected = pyqtSignal(float, object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._original_frame: Optional[np.ndarray] = None
        self._orig_w: int = 1
        self._orig_h: int = 1
        self._start: Optional[QPoint] = None
        self._current_rect: Optional[QRect] = None
        self._confirmed_rect: Optional[QRect] = None
        self._confirmed_area_px: float = 0.0

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(480, 360)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setText("Cargando imagen…")

    # ─── API Pública ──────────────────────────────────────────────────────────

    def set_frame(self, frame_bgr: np.ndarray) -> None:
        """Carga un frame BGR como fondo sobre el que dibujar el rectángulo."""
        self._original_frame = frame_bgr.copy()
        self._orig_h, self._orig_w = frame_bgr.shape[:2]
        self._confirmed_rect = None
        self._confirmed_area_px = 0.0
        self._refresh_pixmap()

    @property
    def confirmed_area_pixels(self) -> float:
        return self._confirmed_area_px

    @property
    def has_selection(self) -> bool:
        return self._confirmed_rect is not None and self._confirmed_area_px > 0

    # ─── Eventos del ratón ────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._original_frame is not None:
            self._start = event.pos()
            self._current_rect = QRect(self._start, self._start)

    def mouseMoveEvent(self, event) -> None:
        if self._start is not None:
            self._current_rect = QRect(self._start, event.pos()).normalized()
            self._refresh_pixmap(draw_rect=self._current_rect)

    def mouseReleaseEvent(self, event) -> None:
        if self._start is not None and event.button() == Qt.MouseButton.LeftButton:
            rect = QRect(self._start, event.pos()).normalized()
            if rect.width() > 5 and rect.height() > 5:
                self._confirmed_rect = rect
                self._confirmed_area_px = self._widget_rect_to_pixels(rect)
                self._current_rect = None
                self._refresh_pixmap(draw_rect=rect, confirmed=True)
                self.area_selected.emit(self._confirmed_area_px, rect)
                logger.debug(
                    "Área seleccionada: %.0f px² (rect widget: %s)",
                    self._confirmed_area_px, rect,
                )
            self._start = None

    # ─── Conversión de coordenadas ────────────────────────────────────────────

    def _widget_rect_to_pixels(self, rect: QRect) -> float:
        """
        Convierte las dimensiones del rectángulo en coordenadas del widget
        al espacio de la imagen original (compensando escalado y márgenes).
        """
        if self._original_frame is None:
            return 0.0

        # Calcular la región donde se pintó la imagen dentro del QLabel
        lw, lh = self.width(), self.height()
        scale = min(lw / self._orig_w, lh / self._orig_h)
        img_w_scaled = int(self._orig_w * scale)
        img_h_scaled = int(self._orig_h * scale)
        offset_x = (lw - img_w_scaled) // 2
        offset_y = (lh - img_h_scaled) // 2

        # Coordenadas relativas al borde de la imagen pintada
        rx = (rect.x() - offset_x) / scale
        ry = (rect.y() - offset_y) / scale
        rw = rect.width() / scale
        rh = rect.height() / scale

        # Clamp dentro de la imagen
        rw = max(0.0, min(rw, self._orig_w - rx))
        rh = max(0.0, min(rh, self._orig_h - ry))

        return rw * rh

    # ─── Renderizado ──────────────────────────────────────────────────────────

    def _refresh_pixmap(
        self,
        draw_rect: Optional[QRect] = None,
        confirmed: bool = False,
    ) -> None:
        if self._original_frame is None:
            return

        # Convertir frame a QPixmap escalado
        rgb = cv2.cvtColor(self._original_frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qt_img = QImage(rgb.tobytes(), w, h, w * ch, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qt_img).scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        # Dibujar rectángulo si aplica
        if draw_rect and not draw_rect.isEmpty():
            painter = QPainter(pixmap)
            color = QColor("#4caf50") if confirmed else QColor("#e94560")
            pen = QPen(color, 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.drawRect(draw_rect)

            if confirmed:
                # Mostrar área en píxeles sobre el rectángulo
                painter.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
                painter.setPen(QColor("#ffffff"))
                label = f"{self._confirmed_area_px:.0f} px²"
                painter.drawText(draw_rect.x() + 4, draw_rect.y() - 6, label)
            painter.end()

        self.setPixmap(pixmap)
