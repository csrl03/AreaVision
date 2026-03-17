"""
Tarjeta de medición para mostrar en la lista del historial.
"""
from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QColor
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame, QSizePolicy,
)

from core.entities import Measurement
from ui.theme import CATEGORY_COLORS


class MeasurementCard(QWidget):
    """
    Tarjeta horizontal con miniatura + nombre + área + categoría + fecha.
    Se usa como widget personalizado dentro de QListWidgetItem.
    """

    def __init__(self, measurement: Measurement, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.measurement = measurement
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)

        # ── Miniatura ──────────────────────────────────────────────────────────
        thumb = QLabel()
        thumb.setFixedSize(QSize(72, 54))
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setStyleSheet("border-radius: 4px; background: #0f0f1a;")
        if self.measurement.silhouette_path and os.path.exists(self.measurement.silhouette_path):
            pix = QPixmap(self.measurement.silhouette_path).scaled(
                QSize(72, 54),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            thumb.setPixmap(pix)
        else:
            thumb.setText("—")
        layout.addWidget(thumb)

        # ── Info central ───────────────────────────────────────────────────────
        info = QVBoxLayout()
        info.setSpacing(2)

        name_lbl = QLabel(self.measurement.display_name)
        name_lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        name_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        info.addWidget(name_lbl)

        meta = QLabel(
            f"{self.measurement.area_m2:.4f} m²  ·  "
            f"{self.measurement.area_cm2:.2f} cm²  ·  "
            f"d={self.measurement.distance_cm:.0f} cm"
        )
        meta.setStyleSheet("color: #a0a0b8; font-size: 11px;")
        info.addWidget(meta)

        date_lbl = QLabel(self.measurement.timestamp.strftime("%d/%m/%Y  %H:%M"))
        date_lbl.setStyleSheet("color: #707080; font-size: 11px;")
        info.addWidget(date_lbl)

        layout.addLayout(info)

        # ── Badge de categoría ─────────────────────────────────────────────────
        cat = self.measurement.category
        color = CATEGORY_COLORS.get(cat.value, "#9e9e9e")

        badge = QLabel(cat.value)
        badge.setFixedSize(QSize(36, 36))
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background-color: {color}; color: #ffffff; "
            f"border-radius: 18px; font-size: 14px; font-weight: bold;"
        )
        layout.addWidget(badge)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
