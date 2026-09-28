"""
Diálogo de revisión del retal — se muestra tras pulsar «Capturar».

El usuario ve el razonamiento completo del sistema **antes** de confirmar:

    Área:                1.37 m²
    Dimensiones:         1.20 × 1.14 m
    Forma:               Rectángulo  (confianza 96 %)
    Regularidad:         Regular  (1.00)
    Espesor:             [ 3.0 ] mm          ← entrada manual
    Valor estimado:      $ 116.450

    Clasificación:       REUTILIZABLE
    Ubicación propuesta: Estante 2 / Repisa 1
    Motivo:              Cumple dimensiones, espesor y reglas de la repisa.

    ⚠ ALERTA DE SEGURIDAD
    La geometría presenta características compatibles con una posible punta…

El usuario puede corregir el espesor, forzar una ubicación distinta o cancelar.
Nada se persiste hasta que confirma.
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QDoubleSpinBox, QComboBox, QLineEdit, QGroupBox, QMessageBox,
    QDialogButtonBox, QApplication,
)

from core.entities import (
    AllocationProposal, Scrap, ScrapAnalysis, ScrapDestination, ScrapStatus,
)
from core.scoring import format_currency

logger = logging.getLogger(__name__)

UNASSIGNED_LABEL = "— Sin asignar (se guardará sin ubicación) —"


class ScrapReviewDialog(QDialog):
    """
    Revisión y confirmación del registro de un retal.

    Atributos de salida (tras `accept()`):
        thickness_mm:    Espesor confirmado por el usuario (o None).
        selected_shelf:  Repisa elegida por el usuario, o None.
        scrap_name:      Nombre capturado.
        notes:           Notas capturadas.
    """

    def __init__(
        self,
        analysis: ScrapAnalysis,
        proposal: AllocationProposal,
        shelves: Optional[list] = None,
        currency_symbol: str = "$",
        contour: Optional[np.ndarray] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._analysis = analysis
        self._proposal = proposal
        self._shelves = shelves or []
        self._contour = contour

        self.thickness_mm: Optional[float] = None
        self.selected_shelf = None
        self.scrap_name: str = ""
        self.notes: str = ""

        self.setWindowTitle("Revisar retal")
        self.setMinimumWidth(560)
        self.setModal(True)
        self._build_ui(currency_symbol)

    # ─── Construcción ─────────────────────────────────────────────────────────

    def _build_ui(self, currency: str) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)

        a, g = self._analysis, self._analysis.geometry

        # ── Título ──
        head = QHBoxLayout()
        title = QLabel("Resumen de la medición")
        title.setObjectName("label_title")
        head.addWidget(title)
        head.addStretch()
        badge = QLabel(a.destination.label_es)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background-color: {a.destination.hex_color}; color: white; "
            f"border-radius: 6px; padding: 5px 14px; font-weight: bold;"
        )
        head.addWidget(badge)
        lay.addLayout(head)

        # ── Métricas ──
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        rows = [
            ("Área", f"{g.area_m2:.4f} m²"),
            ("Dimensiones", g.dimensions_text),
            ("Forma", f"{g.shape.label_es}  (confianza {g.confidence:.0%})"),
            ("Regularidad", f"{g.regularity.label_es}  ({g.regularity_score:.2f})"),
            ("Vértices del contorno", str(g.vertex_count) or "—"),
            ("Valor estimado", format_currency(a.estimated_value, currency)),
        ]
        for i, (k, v) in enumerate(rows):
            kl = QLabel(f"{k}:")
            kl.setStyleSheet("color: #a0a0b8;")
            grid.addWidget(kl, i, 0)
            grid.addWidget(QLabel(v), i, 1)
        lay.addLayout(grid)

        # ── Espesor ──
        th_grp = QGroupBox("Espesor")
        th_lay = QHBoxLayout(th_grp)
        th_lay.addWidget(QLabel("Espesor (mm):"))
        self._sp_thickness = QDoubleSpinBox()
        self._sp_thickness.setRange(0.0, 1000.0)
        self._sp_thickness.setDecimals(2)
        self._sp_thickness.setSingleStep(0.5)
        self._sp_thickness.setValue(a.thickness_mm or 0.0)
        self._sp_thickness.setSpecialValueText("sin capturar")
        self._sp_thickness.setToolTip(
            "La cámara monocular no mide espesor: ingréselo usted.\n"
            "Déjelo en 0 si todavía no lo conoce (no bloquea la clasificación)."
        )
        th_lay.addWidget(self._sp_thickness)
        hint = QLabel(
            "Entrada manual: una cámara monocular no puede medir el espesor.\n"
            "La arquitectura ya admite sustituirla por un sensor."
        )
        hint.setObjectName("label_status")
        th_lay.addWidget(hint, stretch=1)
        th_lay.addStretch()
        lay.addWidget(th_grp)

        # ── Clasificación ──
        cls_grp = QGroupBox("Clasificación")
        cls_lay = QVBoxLayout(cls_grp)
        for reason in a.reasons:
            lbl = QLabel(f"· {reason}")
            lbl.setWordWrap(True)
            cls_lay.addWidget(lbl)
        lay.addWidget(cls_grp)

        # ── Ubicación ──
        loc_grp = QGroupBox("Ubicación")
        loc_lay = QVBoxLayout(loc_grp)

        loc_title = QLabel("Ubicación propuesta:")
        loc_lay.addWidget(loc_title)
        self._lbl_proposal = QLabel("—")
        self._lbl_proposal.setObjectName("label_status")
        self._lbl_proposal.setWordWrap(True)
        loc_lay.addWidget(self._lbl_proposal)
        self._render_proposal()

        if self._shelves:
            row = QHBoxLayout()
            row.addWidget(QLabel("Asignar manualmente a:"))
            self._combo_shelf = QComboBox()
            self._combo_shelf.addItem(UNASSIGNED_LABEL, None)
            for s in self._shelves:
                self._combo_shelf.addItem(
                    f"{s.location_text}  ({s.width_m:.2f}×{s.length_m:.2f} m)", s
                )
            default = next(
                (i for i in range(self._combo_shelf.count())
                 if self._combo_shelf.itemData(i) is self._proposal.shelf),
                0,
            )
            self._combo_shelf.setCurrentIndex(default)
            self._combo_shelf.currentIndexChanged.connect(self._on_manual_shelf)
            row.addWidget(self._combo_shelf, stretch=1)
            loc_lay.addLayout(row)
        lay.addWidget(loc_grp)

        # ── Alerta de seguridad ──
        if a.safety.triggered:
            alert = QGroupBox("⚠ ALERTA DE RIESGO GEOMÉTRICO")
            al = QVBoxLayout(alert)
            msg = QLabel(
                f"Sharpness score: {a.safety.score:.2f}  (umbral aplicado: "
                f"{self._analysis.safety.score:.2f} superada)\n\n"
                "La geometría presenta características compatibles con una posible "
                "punta o borde peligroso.\n\n"
                "⚠ NO constituye una certificación de seguridad industrial. "
                "La manipulación debe seguir el protocolo de su empresa."
            )
            msg.setWordWrap(True)
            msg.setStyleSheet("color: #ff9800;")
            al.addWidget(msg)
            lay.addWidget(alert)

        # ── Identificación ──
        id_grp = QGroupBox("Identificación del retal")
        il = QGridLayout(id_grp)
        il.addWidget(QLabel("Nombre (opcional):"), 0, 0)
        self._in_name = QLineEdit()
        self._in_name.setMaxLength(120)
        self._in_name.setPlaceholderText("Ej: Lámina sala 3")
        il.addWidget(self._in_name, 0, 1)

        il.addWidget(QLabel("Notas (opcional):"), 1, 0)
        self._in_notes = QLineEdit()
        self._in_notes.setMaxLength(250)
        self._in_notes.setPlaceholderText("Descripción adicional…")
        il.addWidget(self._in_notes, 1, 1)
        lay.addWidget(id_grp)

        # ── Botones ──
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Save).setText("Registrar retal")
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _render_proposal(self) -> None:
        p = self._proposal
        if p.found and p.shelf is not None:
            pos = f"posición ({p.position_x_m:.2f}, {p.position_y_m:.2f}) m"
            rot = " — requiere rotación de 90°" if p.rotated else ""
            self._lbl_proposal.setText(
                f"{p.location_text}{rot}\n{pos}\n{p.reason}"
            )
        else:
            self._lbl_proposal.setText(
                f"No se encontró una ubicación física compatible.\n{p.reason}"
            )
            color = "#ff9800" if self._proposal.rejected else "#f44336"
            self._lbl_proposal.setStyleSheet(f"color: {color};")

    def _on_manual_shelf(self, index: int) -> None:
        if hasattr(self, "_combo_shelf"):
            self.selected_shelf = self._combo_shelf.itemData(index)

    # ─── Confirmación ─────────────────────────────────────────────────────────

    def _on_accept(self) -> None:
        self.thickness_mm = self._sp_thickness.value() or None
        self.scrap_name = self._in_name.text().strip() or None
        self.notes = self._in_notes.text().strip() or None
        if hasattr(self, "_combo_shelf"):
            self.selected_shelf = self._combo_shelf.currentData()
        self.accept()

    # ─── Construcción del modelo ──────────────────────────────────────────────

    def build_scrap(self) -> Scrap:
        """
        Construye la entidad `Scrap` a partir de la revisión del usuario.

        Se llama tras `accept()`. Traduce la propuesta automática en la
        asignación definitiva (que puede haber cambiado por la selección manual).
        """
        a, g = self._analysis, self._analysis.geometry
        shelf = self.selected_shelf
        destination = a.destination
        reasons = list(a.reasons)

        if destination == ScrapDestination.REUTILIZABLE and shelf is None:
            reasons.append(
                "Sin ubicación física compatible. El retal queda registrado "
                "como DISPONIBLE pero sin asignar."
            )

        return Scrap(
            name=self.scrap_name,
            area_m2=g.area_m2,
            width_m=g.width_m,
            length_m=g.length_m,
            thickness_mm=self.thickness_mm,
            shape=g.shape,
            regularity=g.regularity,
            shape_confidence=g.confidence,
            regularity_score=g.regularity_score,
            vertex_count=g.vertex_count,
            shelf_id=shelf.id if shelf else None,
            storage_area_id=shelf.storage_area_id if shelf else None,
            destination=destination,
            status=ScrapStatus.DISPONIBLE if destination == ScrapDestination.REUTILIZABLE
                   else ScrapStatus.RECICLADO,
            sharpness_score=a.safety.score,
            safety_alert=a.safety.triggered,
            estimated_value=a.estimated_value,
            cost_per_m2=a.cost_per_m2,
            reasons=reasons,
            shelf_name=shelf.name if shelf else None,
            storage_area_name=shelf.storage_area_name if shelf else None,
        )
