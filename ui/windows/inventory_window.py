"""
Pestaña Inventario — retales reutilizables y destino de reciclaje.

Dos modos de uso:

1. **Listado** — todos los retales registrados, con filtro por destino/estado y
   exportación a DXF.
2. **Buscador de reutilización** — el usuario pide las dimensiones de una pieza
   que necesita fabricar y el sistema devuelve los retales almacenados que la
   cubren, evaluando también la rotación de 90°.

    Necesito:  1.10 m × 0.80 m   →
    Retal #014   1.40 × 1.10 m   1.54 m²   Estante 2 / Repisa 1
"""
from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QDoubleSpinBox, QComboBox,
    QGroupBox, QMessageBox, QDialog, QDialogButtonBox, QFileDialog, QTextEdit,
)

from core.entities import Scrap, ScrapDestination, ScrapStatus, ShapeType
from core.scoring import format_currency
from services.cad_service import CadExportError, CadService
from ui.widgets.scrap_card import ScrapCard

logger = logging.getLogger(__name__)


class ScrapDetailDialog(QDialog):
    """Ficha completa de un retal, con acciones de estado y exportación DXF."""

    def __init__(
        self,
        scrap: Scrap,
        scrap_repo,
        cad_service: Optional[CadService],
        factor_k_provider=None,
        currency_symbol: str = "$",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._scrap = scrap
        self._repo = scrap_repo
        self._cad = cad_service
        self._factor_k = factor_k_provider
        self._currency = currency_symbol
        self.setWindowTitle(f"Detalle — {scrap.display_name}")
        self.setMinimumSize(560, 540)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self) -> None:
        s = self._scrap
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        title = QLabel(s.display_name)
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        lay.addWidget(title)

        badge = QLabel(s.destination.label_es)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            f"background-color: {s.destination.hex_color}; color: white; "
            f"border-radius: 6px; padding: 5px; font-weight: bold;"
        )
        lay.addWidget(badge)

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)
        rows = [
            ("Área", f"{s.area_m2:.4f} m²"),
            ("Dimensiones", s.dimensions_text),
            ("Espesor", f"{s.thickness_mm:.2f} mm" if s.thickness_mm is not None
                        else "No capturado (entrada manual)"),
            ("Forma", s.shape.label_es),
            ("Regularidad", f"{s.regularity.label_es}  ({s.regularity_score:.2f})"
                            if s.regularity_score is not None else s.regularity.label_es),
            ("Confianza de forma", f"{s.shape_confidence:.0%}" if s.shape_confidence is not None else "—"),
            ("Vértices del contorno", str(s.vertex_count) if s.vertex_count else "—"),
            ("Ubicación", s.location_text),
            ("Estado", s.status.label_es),
            ("Valor estimado", format_currency(s.estimated_value, self._currency)),
            ("Fecha de registro", s.created_at.strftime("%d/%m/%Y %H:%M") if s.created_at else "—"),
        ]
        for i, (k, v) in enumerate(rows):
            kl = QLabel(f"{k}:")
            kl.setStyleSheet("color: #a0a0b8;")
            vl = QLabel(v)
            vl.setWordWrap(True)
            grid.addWidget(kl, i, 0)
            grid.addWidget(vl, i, 1)
        lay.addLayout(grid)

        # ── Seguridad ──
        if s.sharpness_score is not None:
            sec = QGroupBox("Riesgo geométrico")
            sl = QVBoxLayout(sec)
            if s.safety_alert:
                sl.addWidget(QLabel(
                    f"⚠ ALERTA — Sharpness score: {s.sharpness_score:.2f}\n"
                    "La geometría presenta rasgos compatibles con una punta o borde "
                    "peligroso.\nNo constituye una certificación de seguridad industrial."
                ))
            else:
                sl.addWidget(QLabel(
                    f"Sin alerta de riesgo geométrico (score {s.sharpness_score:.2f})."
                ))
            lay.addWidget(sec)

        # ── Motivos ──
        if s.reasons:
            why = QGroupBox("Motivos de la clasificación")
            wl = QVBoxLayout(why)
            for r in s.reasons:
                wl.addWidget(QLabel(f"· {r}"))
            lay.addWidget(why)

        # ── Acciones ──
        acts = QHBoxLayout()
        self._combo_status = QComboBox()
        for st in ScrapStatus:
            self._combo_status.addItem(st.label_es, st)
        current = self._combo_status.findData(s.status)
        if current >= 0:
            self._combo_status.setCurrentIndex(current)
        acts.addWidget(self._combo_status)

        btn_status = QPushButton("Cambiar estado")
        btn_status.setObjectName("btn_secondary")
        btn_status.clicked.connect(self._on_change_status)
        acts.addWidget(btn_status)

        acts.addStretch()
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.reject)
        acts.addWidget(btns)
        lay.addLayout(acts)

        # ── DXF ──
        dxf_grp = QGroupBox("Exportar plano DXF")
        dl = QVBoxLayout(dxf_grp)
        hint = QLabel(
            "El DXF se genera a partir del contorno real detectado por la cámara, "
            "simplificado geométricamente y escalado de píxeles a milímetros."
        )
        hint.setObjectName("label_status")
        hint.setWordWrap(True)
        dl.addWidget(hint)

        brow = QHBoxLayout()
        btn_contour = QPushButton("Desde la silueta guardada")
        btn_contour.setObjectName("btn_calibrate")
        btn_contour.clicked.connect(self._on_export_silhouette)
        brow.addWidget(btn_contour)

        btn_rect = QPushButton("Desde las dimensiones")
        btn_rect.setObjectName("btn_secondary")
        btn_rect.clicked.connect(self._on_export_rect)
        brow.addWidget(btn_rect)
        dl.addLayout(brow)
        lay.addWidget(dxf_grp)

    # ─── Acciones ─────────────────────────────────────────────────────────────

    def _on_change_status(self) -> None:
        status = self._combo_status.currentData()
        if status is None:
            return
        self._repo.set_status(self._scrap.id, status)
        self._scrap.status = status
        QMessageBox.information(self, "Estado actualizado",
                                f"{self._scrap.display_name} → {status.label_es}")

    def _current_factor_k(self) -> Optional[float]:
        if self._factor_k is None:
            return None
        try:
            return float(self._factor_k())
        except Exception:
            return None

    def _on_export_silhouette(self) -> None:
        if self._cad is None:
            QMessageBox.information(self, "Sin servicio CAD", "El servicio CAD no está disponible.")
            return
        fk = self._current_factor_k()
        if fk is None or fk <= 0:
            QMessageBox.warning(
                self, "Sin calibración",
                "El escalado píxeles → milímetros requiere la calibración activa.\n"
                "Vaya a Configuración → Nueva calibración.",
            )
            return
        try:
            path = self._cad.export_from_silhouette(self._scrap.silhouette_path, fk, self._scrap)
        except CadExportError as exc:
            QMessageBox.warning(
                self, "No se pudo exportar",
                f"{exc}\n\n¿Desea exportar el rectángulo mínimo en su lugar?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            ) == QMessageBox.StandardButton.Yes and self._on_export_rect()
            return
        QMessageBox.information(self, "DXF generado", f"Contorno exportado:\n{path}")

    def _on_export_rect(self) -> None:
        if self._cad is None:
            QMessageBox.information(self, "Sin servicio CAD", "El servicio CAD no está disponible.")
            return
        try:
            path = self._cad.export_scrap_rectangle(self._scrap)
        except CadExportError as exc:
            QMessageBox.critical(self, "Error al exportar", str(exc))
            return
        QMessageBox.information(
            self, "DXF generado",
            f"Rectángulo exportado (en metros):\n{path}\n\n"
            "Esta es la geometría que el sistema conoce con certeza; "
            "no es el contorno real de la pieza.",
        )


class InventoryWindow(QWidget):
    """
    Inventario de retales y buscador de reutilización.

    Señales:
        data_changed(): emitida tras cambiar estados o eliminar retales.
    """

    data_changed = pyqtSignal()

    def __init__(
        self,
        scrap_repo,
        cad_service: Optional[CadService] = None,
        settings_repo=None,
        factor_k_provider=None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._repo = scrap_repo
        self._cad = cad_service
        self._settings_repo = settings_repo
        self._factor_k = factor_k_provider
        self._items: list[Scrap] = []

        self._build_ui()
        self.reload()

    def _currency(self) -> str:
        if self._settings_repo is None:
            return "$"
        try:
            return str(self._settings_repo.get().get("currency_symbol", "$"))
        except Exception:
            return "$"

    # ─── Construcción ─────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ── Resumen ──
        self._lbl_summary = QLabel("—")
        self._lbl_summary.setObjectName("label_status")
        root.addWidget(self._lbl_summary)

        # ── Filtros ──
        filt = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Buscar por nombre…")
        self._search.textChanged.connect(self.reload)
        filt.addWidget(self._search, stretch=2)

        self._combo_dest = QComboBox()
        self._combo_dest.addItem("Todos los destinos", None)
        self._combo_dest.addItem("Solo reutilizables", ScrapDestination.REUTILIZABLE)
        self._combo_dest.addItem("Solo reciclaje", ScrapDestination.RECICLABLE)
        self._combo_dest.currentIndexChanged.connect(self.reload)
        filt.addWidget(self._combo_dest, stretch=1)

        btn_reuse = QPushButton("Buscar pieza a fabricar")
        btn_reuse.setObjectName("btn_calibrate")
        btn_reuse.clicked.connect(self._on_open_reuse_search)
        filt.addWidget(btn_reuse)

        btn_del = QPushButton("Eliminar seleccionado")
        btn_del.setObjectName("btn_danger")
        btn_del.clicked.connect(self._on_delete)
        filt.addWidget(btn_del)
        root.addLayout(filt)

        # ── Lista ──
        self._list = QListWidget()
        self._list.setSpacing(2)
        self._list.setAlternatingRowColors(True)
        self._list.itemDoubleClicked.connect(self._on_open_detail)
        root.addWidget(self._list, stretch=1)

        self._lbl_count = QLabel("0 retal(es)")
        self._lbl_count.setObjectName("label_status")
        root.addWidget(self._lbl_count)

        # ── Buscador de reutilización ──
        root.addWidget(self._build_reuse_panel())

    def _build_reuse_panel(self) -> QWidget:
        grp = QGroupBox("Necesito fabricar una pieza — buscar retales compatibles")
        lay = QVBoxLayout(grp)

        row = QHBoxLayout()
        row.addWidget(QLabel("Ancho requerido (m):"))
        self._sp_req_w = QDoubleSpinBox()
        self._sp_req_w.setRange(0.01, 50.0)
        self._sp_req_w.setDecimals(2)
        self._sp_req_w.setValue(1.10)
        row.addWidget(self._sp_req_w)

        row.addWidget(QLabel("Largo requerido (m):"))
        self._sp_req_l = QDoubleSpinBox()
        self._sp_req_l.setRange(0.01, 50.0)
        self._sp_req_l.setDecimals(2)
        self._sp_req_l.setValue(0.80)
        row.addWidget(self._sp_req_l)

        row.addWidget(QLabel("Espesor mín. (mm):"))
        self._sp_req_t = QDoubleSpinBox()
        self._sp_req_t.setRange(0.0, 1000.0)
        self._sp_req_t.setDecimals(1)
        self._sp_req_t.setSpecialValueText("cualquiera")
        row.addWidget(self._sp_req_t)

        btn = QPushButton("Buscar")
        btn.clicked.connect(self._on_search_piece)
        row.addWidget(btn)
        row.addStretch()
        lay.addLayout(row)

        self._txt_results = QTextEdit()
        self._txt_results.setReadOnly(True)
        self._txt_results.setMaximumHeight(150)
        self._txt_results.setPlaceholderText(
            "Los resultados aparecen aquí. Un retal sirve si cubre la pieza "
            "en alguna de sus dos orientaciones."
        )
        lay.addWidget(self._txt_results)
        return grp

    # ─── Carga ────────────────────────────────────────────────────────────────

    def reload(self) -> None:
        try:
            items = self._repo.get_all()
        except Exception as exc:  # pragma: no cover
            logger.warning("No se pudo leer el inventario: %s", exc)
            items = []

        text = self._search.text().strip().lower()
        if text:
            items = [s for s in items if text in (s.name or "").lower()]

        dest = self._combo_dest.currentData()
        if dest is not None:
            items = [s for s in items if s.destination == dest]

        self._items = items
        currency = self._currency()
        self._list.clear()
        for s in items:
            card = ScrapCard(s, currency)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, s.id)
            item.setSizeHint(card.sizeHint())
            self._list.addItem(item)
            self._list.setItemWidget(item, card)
        self._lbl_count.setText(f"{len(items)} retal(es)")

        try:
            st = self._repo.get_statistics()
        except Exception:
            st = {}
        if st:
            self._lbl_summary.setText(
                f"Total: {st['total']} retal(es)  ·  {st['total_area']:.2f} m²  ·  "
                f"Reutilizable: {st['reusable_area']:.2f} m²  ·  "
                f"Reciclaje: {st['recyclable_area']:.2f} m²  ·  "
                f"Valor: {format_currency(st['total_value'], currency)}  ·  "
                f"Alertas de riesgo: {st['safety_alerts']}  ·  "
                f"Sin ubicación: {st['unassigned']}"
            )

    # ─── Acciones ─────────────────────────────────────────────────────────────

    def _on_open_detail(self, item: QListWidgetItem) -> None:
        scrap_id = item.data(Qt.ItemDataRole.UserRole)
        scrap = next((s for s in self._items if s.id == scrap_id), None)
        if scrap is None:
            return
        dlg = ScrapDetailDialog(
            scrap, self._repo, self._cad, self._factor_k, self._currency(), self
        )
        dlg.exec()
        self.reload()
        self.data_changed.emit()

    def _on_delete(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        scrap_id = item.data(Qt.ItemDataRole.UserRole)
        scrap = next((s for s in self._items if s.id == scrap_id), None)
        if scrap is None:
            return
        reply = QMessageBox.question(
            self, "Confirmar",
            f"¿Eliminar «{scrap.display_name}» del inventario?\n"
            "La medición asociada se conserva en el historial.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._repo.delete(scrap_id)
            self.reload()
            self.data_changed.emit()

    def _on_open_reuse_search(self) -> None:
        self._on_search_piece()
        self._txt_results.setFocus()

    def _on_search_piece(self) -> None:
        w = self._sp_req_w.value()
        h = self._sp_req_l.value()
        t = self._sp_req_t.value() or None
        try:
            found = self._repo.search(min_width_m=w, min_length_m=h, min_thickness_mm=t)
        except Exception as exc:  # pragma: no cover
            QMessageBox.critical(self, "Error en la búsqueda", str(exc))
            return

        currency = self._currency()
        if not found:
            self._txt_results.setText(
                f"No hay retales almacenados que cubran {w:.2f} × {h:.2f} m.\n\n"
                "Un retal serviría si, en alguna de sus dos orientaciones, "
                "sus lados cubren al menos los solicitados."
            )
            return

        lines = [
            f"{len(found)} retal(es) compatibles con {w:.2f} × {h:.2f} m:",
            "",
        ]
        for s in found:
            lines.append(
                f"{s.display_name}\n"
                f"    Dimensiones: {s.dimensions_text}\n"
                f"    Área:        {s.area_m2:.4f} m²\n"
                f"    Espesor:     "
                f"{f'{s.thickness_mm:.1f} mm' if s.thickness_mm is not None else 'no capturado'}\n"
                f"    Forma:       {s.shape.label_es} ({s.regularity.label_es})\n"
                f"    Ubicación:   {s.location_text}\n"
                f"    Valor:       {format_currency(s.estimated_value, currency)}\n"
            )
        self._txt_results.setText("\n".join(lines))
