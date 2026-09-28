"""
Tarjeta de retal para la lista de inventario.

Réplica visual de `ui/widgets/measurement_card.py`: misma estructura
(miniatura + datos + badge), para que las dos listas de la app se lean igual.
"""
from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QSizePolicy,
)

from core.entities import Scrap, ScrapDestination
from core.scoring import format_currency

SHARPNESS_ALERT_ICON = "⚠"


class ScrapCard(QWidget):
    """
    Tarjeta horizontal con miniatura, dimensiones, forma, ubicación y destino.

    Se usa como widget personalizado dentro de un QListWidgetItem.
    """

    def __init__(self, scrap: Scrap, currency_symbol: str = "$", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.scrap = scrap
        self._currency_symbol = currency_symbol
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(12)

        # ── Miniatura ──
        thumb = QLabel()
        thumb.setFixedSize(QSize(72, 54))
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setStyleSheet("border-radius: 4px; background: #0f0f1a;")
        if self.scrap.silhouette_path and os.path.exists(self.scrap.silhouette_path):
            pix = QPixmap(self.scrap.silhouette_path).scaled(
                QSize(72, 54),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            thumb.setPixmap(pix)
        else:
            thumb.setText("—")
        layout.addWidget(thumb)

        # ── Datos ──
        info = QVBoxLayout()
        info.setSpacing(2)

        name = QLabel(self.scrap.display_name)
        name.setStyleSheet("font-weight: bold; font-size: 13px;")
        name.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        info.addWidget(name)

        thickness = (
            f"{self.scrap.thickness_mm:.1f} mm" if self.scrap.thickness_mm is not None
            else "espesor s/d"
        )
        meta = QLabel(
            f"{self.scrap.dimensions_text}  ·  {self.scrap.area_m2:.3f} m²  ·  {thickness}"
        )
        meta.setStyleSheet("color: #a0a0b8; font-size: 11px;")
        info.addWidget(meta)

        detail = QLabel(
            f"{self.scrap.shape.label_es} · {self.scrap.regularity.label_es}"
            f"  ·  {self.scrap.location_text}"
        )
        detail.setStyleSheet("color: #707080; font-size: 11px;")
        info.addWidget(detail)

        layout.addLayout(info)

        # ── Valor ──
        value = QLabel(format_currency(self.scrap.estimated_value, self._currency_symbol))
        value.setStyleSheet("color: #9ccc65; font-size: 12px; font-weight: bold;")
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(value)

        # ── Badge de destino ──
        badge = QLabel(self.scrap.destination.label_es[:4])
        badge.setFixedSize(QSize(46, 30))
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setToolTip(
            f"Destino: {self.scrap.destination.label_es}\n"
            + ("\n".join(f"· {r}" for r in self.scrap.reasons) if self.scrap.reasons else "")
        )
        badge.setStyleSheet(
            f"background-color: {self.scrap.destination.hex_color}; color: #ffffff; "
            f"border-radius: 6px; font-size: 10px; font-weight: bold;"
        )
        layout.addWidget(badge)

        # ── Indicador de riesgo geométrico ──
        if self.scrap.safety_alert:
            alert = QLabel(f"{SHARPNESS_ALERT_ICON} {self.scrap.sharpness_score:.2f}")
            alert.setStyleSheet("color: #ff9800; font-size: 12px; font-weight: bold;")
            alert.setToolTip(
                "Geometría potencialmente punzante.\n"
                "No constituye una certificación de seguridad industrial."
            )
            layout.addWidget(alert)

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
