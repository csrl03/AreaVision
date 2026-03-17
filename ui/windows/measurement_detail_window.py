"""
Ventana de detalle de medición guardada.
"""
from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QScrollArea, QWidget, QMessageBox,
)

from core.entities import Measurement
from ui.theme import CATEGORY_COLORS


class MeasurementDetailWindow(QDialog):
    """
    Muestra todos los metadatos de una medición guardada.

    Señal:
        deleted(int): emitida con el ID de la medición cuando el usuario la elimina.
    """
    deleted = pyqtSignal(int)

    def __init__(self, measurement: Measurement, parent=None) -> None:
        super().__init__(parent)
        self._measurement = measurement
        self.setWindowTitle(f"Detalle — {measurement.display_name}")
        self.setMinimumSize(560, 500)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        m = self._measurement
        cat = m.category
        cat_color = CATEGORY_COLORS.get(cat.value, "#9e9e9e")

        # ── Encabezado ──────────────────────────────────────────────────────────
        header = QHBoxLayout()

        # Miniatura
        thumb = QLabel()
        thumb.setFixedSize(160, 120)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setStyleSheet("border-radius: 6px; background: #0a0a18;")
        if m.silhouette_path and os.path.exists(m.silhouette_path):
            pix = QPixmap(m.silhouette_path).scaled(
                160, 120,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            thumb.setPixmap(pix)
        else:
            thumb.setText("Sin imagen")
        header.addWidget(thumb)

        # Info principal
        info_lay = QVBoxLayout()
        name_lbl = QLabel(m.display_name)
        name_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        info_lay.addWidget(name_lbl)

        area_lbl = QLabel(f"{m.area_m2:.4f} m²   /   {m.area_cm2:.2f} cm²")
        area_lbl.setStyleSheet("font-size: 22px; font-weight: bold;")
        info_lay.addWidget(area_lbl)

        cat_badge = QLabel(cat.label_es)
        cat_badge.setStyleSheet(
            f"background-color: {cat_color}; color: white; "
            f"border-radius: 8px; padding: 4px 14px; font-size: 14px; font-weight: bold;"
        )
        cat_badge.setFixedHeight(32)
        info_lay.addWidget(cat_badge)

        date_lbl = QLabel(m.timestamp.strftime("%d/%m/%Y  %H:%M:%S"))
        date_lbl.setStyleSheet("color: #888; font-size: 12px;")
        info_lay.addWidget(date_lbl)

        info_lay.addStretch()
        header.addLayout(info_lay)
        lay.addLayout(header)

        # ── Métricas ───────────────────────────────────────────────────────────
        metrics_grp = QGroupBox("Métricas técnicas")
        metrics_lay = QVBoxLayout(metrics_grp)

        rows = [
            ("ID",                 str(m.id)),
            ("Área en píxeles",    f"{m.area_pixels:.0f} px²"),
            ("Perímetro",          f"{m.perimeter_pixels:.0f} px" if m.perimeter_pixels else "—"),
            ("Circularidad",       f"{m.circularity:.3f}" if m.circularity is not None else "—"),
            ("FactorK usado",      f"{m.factor_k_used:.4e} m²/px²"),
            ("Distancia medición", f"{m.distance_cm:.1f} cm"),
            ("Confianza",          f"{m.confidence * 100:.0f}%" if m.confidence else "—"),
            ("Notas",              m.notes or "—"),
        ]
        for label, value in rows:
            row = QHBoxLayout()
            lbl = QLabel(f"{label}:")
            lbl.setFixedWidth(160)
            lbl.setStyleSheet("color: #888; font-size: 12px;")
            val = QLabel(value)
            val.setStyleSheet("font-size: 12px;")
            row.addWidget(lbl)
            row.addWidget(val)
            row.addStretch()
            metrics_lay.addLayout(row)

        lay.addWidget(metrics_grp)

        # ── Acciones ───────────────────────────────────────────────────────────
        actions = QHBoxLayout()
        actions.addStretch()

        btn_del = QPushButton("Eliminar medición")
        btn_del.setObjectName("btn_danger")
        btn_del.clicked.connect(self._on_delete)
        actions.addWidget(btn_del)

        btn_close = QPushButton("Cerrar")
        btn_close.setObjectName("btn_secondary")
        btn_close.clicked.connect(self.reject)
        actions.addWidget(btn_close)

        lay.addLayout(actions)

    def _on_delete(self) -> None:
        reply = QMessageBox.question(
            self, "Confirmar eliminación",
            f"¿Eliminar la medición '{self._measurement.display_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.deleted.emit(self._measurement.id)
            self.accept()
