"""
Pestaña Almacén — CRUD de estantes y repisas.

Estructura visual:

    ┌────────────────┬─────────────────────────────────────────┐
    │ Árbol          │ Detalle de la repisa seleccionada        │
    │                │                                         │
    │ Estante 1      │  Dimensiones:  2.00 × 1.20 m             │
    │   Repisa 1     │  Capacidad:    2.40 m²                   │
    │   Repisa 2     │  Ocupación:    ▓▓▓▓▓░░░  58 %            │
    │ Estante 2      │  Libre:        1.01 m²                   │
    │   Repisa 1     │  Retales:      3                         │
    │                │                                         │
    │ [+ Estante]    │  Reglas de aceptación                    │
    │ [+ Repisa]     │  [x] regulares  [ ] irregulares          │
    │                │  ancho  0.50 – 2.00 m                    │
    │                │  ...                                     │
    │                │  [Guardar] [DXF] [Eliminar]              │
    └────────────────┴─────────────────────────────────────────┘

El usuario define la estructura física; el sistema nunca la presupone.
"""
from __future__ import annotations

import logging
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QTreeWidget, QTreeWidgetItem, QLineEdit, QDoubleSpinBox, QCheckBox,
    QGroupBox, QMessageBox, QFileDialog, QProgressBar, QFrame,
)

from core.entities import Scrap, Shelf, ShelfRules, StorageArea
from services.cad_service import CadExportError, CadService
from ui.theme import OCCUPANCY_COLORS

logger = logging.getLogger(__name__)


def _spin(lo: float, hi: float, dec: int = 2, step: float = 0.1) -> QDoubleSpinBox:
    """Spinbox con decimales 0 = 'sin límite' permitido (se traduce a None)."""
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setDecimals(dec)
    s.setSingleStep(step)
    s.setSpecialValueText("sin límite")
    return s


def _val(spin: QDoubleSpinBox) -> Optional[float]:
    """Convierte el spinbox a None cuando está en el valor centinela 0."""
    v = spin.value()
    return None if v <= 0 else v


class StorageWindow(QWidget):
    """
    Gestor del almacén físico.

    Señales:
        data_changed(): emitida tras cualquier alta, edición o baja, para que
        otras pestañas (inventario) se refresquen.
    """

    data_changed = pyqtSignal()

    def __init__(
        self,
        storage_repo,
        shelf_repo,
        scrap_repo,
        cad_service: Optional[CadService] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._storage_repo = storage_repo
        self._shelf_repo = shelf_repo
        self._scrap_repo = scrap_repo
        self._cad = cad_service
        self._shelves: list[Shelf] = []
        self._current_shelf: Optional[Shelf] = None
        self._loading = False  # evita disparar señales durante el relleno

        self._build_ui()
        self.reload()

    # ─── Construcción ─────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # ── Árbol ──
        left = QVBoxLayout()
        left.setSpacing(6)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels(["Almacén", "Dimensiones", "Ocupación"])
        self._tree.setColumnWidth(0, 190)
        self._tree.setColumnWidth(1, 120)
        self._tree.setColumnWidth(2, 80)
        self._tree.itemSelectionChanged.connect(self._on_tree_selection)
        left.addWidget(self._tree, stretch=1)

        btn_row = QHBoxLayout()
        self._btn_add_area = QPushButton("+ Estante")
        self._btn_add_area.setObjectName("btn_calibrate")
        self._btn_add_area.clicked.connect(self._on_add_area)
        btn_row.addWidget(self._btn_add_area)

        self._btn_add_shelf = QPushButton("+ Repisa")
        self._btn_add_shelf.clicked.connect(self._on_add_shelf)
        btn_row.addWidget(self._btn_add_shelf)

        self._btn_del = QPushButton("Eliminar")
        self._btn_del.setObjectName("btn_danger")
        self._btn_del.clicked.connect(self._on_delete)
        btn_row.addWidget(self._btn_del)
        left.addLayout(btn_row)

        tree_widget = QWidget()
        tree_widget.setLayout(left)
        tree_widget.setFixedWidth(470)
        root.addWidget(tree_widget)

        # ── Detalle ──
        self._detail = self._build_detail()
        root.addWidget(self._detail, stretch=1)

    def _build_detail(self) -> QWidget:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        title = QLabel("Seleccione una repisa")
        title.setObjectName("label_title")
        lay.addWidget(title)
        self._lbl_title = title

        # ── Identidad ──
        id_grp = QGroupBox("Identificación")
        id_lay = QGridLayout(id_grp)
        id_lay.setHorizontalSpacing(12)
        id_lay.setVerticalSpacing(8)

        id_lay.addWidget(QLabel("Nombre:"), 0, 0)
        self._in_name = QLineEdit()
        self._in_name.setMaxLength(80)
        self._in_name.setPlaceholderText("Repisa 1")
        id_lay.addWidget(self._in_name, 0, 1)

        id_lay.addWidget(QLabel("Ancho (m):"), 1, 0)
        self._sp_width = QDoubleSpinBox()
        self._sp_width.setRange(0.01, 50.0)
        self._sp_width.setDecimals(2)
        self._sp_width.setSingleStep(0.1)
        self._sp_width.setValue(2.0)
        self._sp_width.setToolTip("Dimensión del lado X de la repisa.")
        id_lay.addWidget(self._sp_width, 1, 1)

        id_lay.addWidget(QLabel("Largo (m):"), 2, 0)
        self._sp_length = QDoubleSpinBox()
        self._sp_length.setRange(0.01, 50.0)
        self._sp_length.setDecimals(2)
        self._sp_length.setSingleStep(0.1)
        self._sp_length.setValue(1.2)
        self._sp_length.setToolTip("Dimensión del lado Y de la repisa.")
        id_lay.addWidget(self._sp_length, 2, 1)

        id_lay.addWidget(QLabel("Capacidad:"), 3, 0)
        self._lbl_capacity = QLabel("—")
        self._lbl_capacity.setObjectName("label_status")
        id_lay.addWidget(self._lbl_capacity, 3, 1)
        lay.addWidget(id_grp)

        # ── Ocupación ──
        occ_grp = QGroupBox("Ocupación")
        occ_lay = QVBoxLayout(occ_grp)
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setFormat("%p %")
        occ_lay.addWidget(self._bar)
        self._lbl_occ = QLabel("—")
        self._lbl_occ.setObjectName("label_status")
        self._lbl_occ.setWordWrap(True)
        # Sin altura mínima el QGroupBox recorta la segunda línea del texto,
        # que es justamente la advertencia sobre el espacio libre por área.
        self._lbl_occ.setMinimumHeight(34)
        occ_lay.addWidget(self._lbl_occ)
        lay.addWidget(occ_grp)

        # ── Reglas ──
        rules_grp = QGroupBox("Reglas de aceptación")
        rules_lay = QGridLayout(rules_grp)
        rules_lay.setHorizontalSpacing(12)
        rules_lay.setVerticalSpacing(8)

        self._chk_regular = QCheckBox("Admite formas regulares")
        self._chk_regular.setChecked(True)
        self._chk_regular.setToolTip(
            "Cuadrado, rectángulo, círculo, triángulo y polígono regular (5-8 lados)."
        )
        self._chk_irregular = QCheckBox("Admite formas irregulares")
        self._chk_irregular.setChecked(True)
        self._chk_irregular.setToolTip("Polígono irregular y formas no reconocidas.")
        rules_lay.addWidget(self._chk_regular, 0, 0, 1, 2)
        rules_lay.addWidget(self._chk_irregular, 1, 0, 1, 2)

        self._spin_min_w = _spin(0.0, 50.0)
        self._spin_max_w = _spin(0.0, 50.0)
        self._spin_min_l = _spin(0.0, 50.0)
        self._spin_max_l = _spin(0.0, 50.0)
        self._spin_min_a = _spin(0.0, 500.0)
        self._spin_max_a = _spin(0.0, 500.0)
        self._spin_min_t = _spin(0.0, 1000.0, dec=1, step=0.5)
        self._spin_max_t = _spin(0.0, 1000.0, dec=1, step=0.5)
        for s, tip in (
            (self._spin_min_w, "Ancho mínimo admitido (lado corto)."),
            (self._spin_max_w, "Ancho máximo admitido (lado corto)."),
            (self._spin_min_l, "Largo mínimo admitido (lado largo)."),
            (self._spin_max_l, "Largo máximo admitido (lado largo)."),
            (self._spin_min_a, "Área mínima en m²."),
            (self._spin_max_a, "Área máxima en m²."),
            (self._spin_min_t, "Espesor mínimo en mm."),
            (self._spin_max_t, "Espesor máximo en mm."),
        ):
            s.setToolTip(tip)

        rules_lay.addWidget(QLabel("Ancho (m):"), 2, 0)
        rules_lay.addWidget(self._spin_min_w, 2, 1)
        rules_lay.addWidget(QLabel("a"), 2, 2)
        rules_lay.addWidget(self._spin_max_w, 2, 3)

        rules_lay.addWidget(QLabel("Largo (m):"), 3, 0)
        rules_lay.addWidget(self._spin_min_l, 3, 1)
        rules_lay.addWidget(QLabel("a"), 3, 2)
        rules_lay.addWidget(self._spin_max_l, 3, 3)

        rules_lay.addWidget(QLabel("Área (m²):"), 4, 0)
        rules_lay.addWidget(self._spin_min_a, 4, 1)
        rules_lay.addWidget(QLabel("a"), 4, 2)
        rules_lay.addWidget(self._spin_max_a, 4, 3)

        rules_lay.addWidget(QLabel("Espesor (mm):"), 5, 0)
        rules_lay.addWidget(self._spin_min_t, 5, 1)
        rules_lay.addWidget(QLabel("a"), 5, 2)
        rules_lay.addWidget(self._spin_max_t, 5, 3)

        note = QLabel(
            "Deja un límite en 0 para que la repisa acepte cualquier valor en ese extremo.\n"
            "Un retal puede girarse 90°: los límites se evalúan sobre ambos lados."
        )
        note.setObjectName("label_status")
        note.setWordWrap(True)
        rules_lay.addWidget(note, 6, 0, 1, 4)
        lay.addWidget(rules_grp)

        # ── Acciones ──
        actions = QHBoxLayout()
        self._btn_save = QPushButton("Guardar cambios")
        self._btn_save.setObjectName("btn_calibrate")
        self._btn_save.clicked.connect(self._on_save)
        actions.addWidget(self._btn_save)

        self._btn_dxf = QPushButton("Exportar DXF de la repisa")
        self._btn_dxf.setObjectName("btn_secondary")
        self._btn_dxf.clicked.connect(self._on_export_dxf)
        actions.addWidget(self._btn_dxf)

        actions.addStretch()
        lay.addLayout(actions)

        # ── Contenido ──
        content = QGroupBox("Retales almacenados")
        content_lay = QVBoxLayout(content)
        self._lbl_content = QLabel("Sin retales en esta repisa.")
        self._lbl_content.setObjectName("label_status")
        self._lbl_content.setWordWrap(True)
        self._lbl_content.setAlignment(Qt.AlignmentFlag.AlignTop)
        content_lay.addWidget(self._lbl_content)
        lay.addWidget(content, stretch=1)

        self._set_detail_enabled(False)
        return wrap

    # ─── Carga ────────────────────────────────────────────────────────────────

    def reload(self) -> None:
        """Recarga estantes, repisas y ocupación desde la base de datos."""
        self._loading = True
        try:
            areas = self._storage_repo.get_all()
            self._shelves = self._shelf_repo.get_all()
            by_area: dict[int, list[Shelf]] = {}
            for s in self._shelves:
                by_area.setdefault(s.storage_area_id, []).append(s)

            self._tree.clear()
            for area in areas:
                parent = QTreeWidgetItem(self._tree, [area.display_name, "", ""])
                parent.setData(0, Qt.ItemDataRole.UserRole, ("area", area.id))
                shelves = by_area.get(area.id, [])
                for s in shelves:
                    ratio = s.occupancy_ratio
                    color = (OCCUPANCY_COLORS["low"] if ratio < 0.6
                             else OCCUPANCY_COLORS["mid"] if ratio < 0.9
                             else OCCUPANCY_COLORS["high"])
                    child = QTreeWidgetItem(parent, [
                        s.display_name,
                        f"{s.width_m:.2f} × {s.length_m:.2f}",
                        f"{ratio * 100:.0f} %",
                    ])
                    child.setData(0, Qt.ItemDataRole.UserRole, ("shelf", s.id))
                    # Semáforo de ocupación: verde < 60 %, ámbar < 90 %, rojo ≥ 90 %.
                    child.setForeground(2, QBrush(QColor(color)))
                    child.setForeground(1, QBrush(QColor("#8a8a9a")))
                    child.setToolTip(2, f"Ocupación {ratio * 100:.0f} %")
                parent.setExpanded(True)

            if not areas:
                QTreeWidgetItem(self._tree, [
                    "Sin estantes — use «+ Estante» para empezar", "", ""
                ])
        finally:
            self._loading = False

        if self._current_shelf is not None:
            match = next((s for s in self._shelves if s.id == self._current_shelf.id), None)
            self._current_shelf = match
            if match is None:
                self._clear_detail()
        self._refresh_content()

    def _on_tree_selection(self) -> None:
        if self._loading:
            return
        items = self._tree.selectedItems()
        if not items:
            return
        kind, obj_id = items[0].data(0, Qt.ItemDataRole.UserRole)
        if kind != "shelf":
            self._clear_detail()
            return
        shelf = next((s for s in self._shelves if s.id == obj_id), None)
        if shelf is not None:
            self._select_shelf(shelf)

    def _select_shelf(self, shelf: Shelf) -> None:
        self._current_shelf = shelf
        self._loading = True
        try:
            self._in_name.setText(shelf.name)
            self._sp_width.setValue(shelf.width_m)
            self._sp_length.setValue(shelf.length_m)
            r = shelf.rules
            self._chk_regular.setChecked(r.accepts_regular)
            self._chk_irregular.setChecked(r.accepts_irregular)
            self._spin_min_w.setValue(r.min_width_m or 0)
            self._spin_max_w.setValue(r.max_width_m or 0)
            self._spin_min_l.setValue(r.min_length_m or 0)
            self._spin_max_l.setValue(r.max_length_m or 0)
            self._spin_min_a.setValue(r.min_area_m2 or 0)
            self._spin_max_a.setValue(r.max_area_m2 or 0)
            self._spin_min_t.setValue(r.min_thickness_mm or 0)
            self._spin_max_t.setValue(r.max_thickness_mm or 0)
        finally:
            self._loading = False

        self._lbl_title.setText(f"{shelf.location_text}")
        self._lbl_capacity.setText(f"{shelf.area_m2:.3f} m²")
        self._update_occupancy(shelf)
        self._refresh_content()
        self._set_detail_enabled(True)

    def _clear_detail(self) -> None:
        self._current_shelf = None
        self._lbl_title.setText("Seleccione una repisa")
        self._lbl_capacity.setText("—")
        self._lbl_occ.setText("—")
        self._bar.setValue(0)
        self._set_detail_enabled(False)

    def _set_detail_enabled(self, enabled: bool) -> None:
        for w in (self._in_name, self._sp_width, self._sp_length,
                  self._chk_regular, self._chk_irregular,
                  self._spin_min_w, self._spin_max_w, self._spin_min_l, self._spin_max_l,
                  self._spin_min_a, self._spin_max_a, self._spin_min_t, self._spin_max_t,
                  self._btn_save, self._btn_dxf):
            w.setEnabled(enabled)

    def _update_occupancy(self, shelf: Shelf) -> None:
        pct = int(round(shelf.occupancy_ratio * 100))
        self._bar.setValue(min(100, pct))
        self._lbl_occ.setText(
            f"Ocupado: {shelf.used_area_m2:.3f} m² de {shelf.area_m2:.3f} m²   ·   "
            f"Libre por área: {shelf.available_area_m2:.3f} m²   ·   "
            f"{shelf.scrap_count} retal(es)\n"
            "El espacio libre por área es una estimación: dos retales cuya suma cabe "
            "pueden no caber juntos."
        )

    def _refresh_content(self) -> None:
        if self._current_shelf is None or self._scrap_repo is None:
            self._lbl_content.setText("Sin retales en esta repisa.")
            return
        try:
            items: list[Scrap] = self._scrap_repo.get_by_shelf(self._current_shelf.id)
        except Exception as exc:  # pragma: no cover
            logger.warning("No se pudieron leer los retales de la repisa: %s", exc)
            items = []

        if not items:
            self._lbl_content.setText("Sin retales en esta repisa.")
            return

        lines = []
        for s in items:
            thick = f"{s.thickness_mm:.1f} mm" if s.thickness_mm is not None else "s/d"
            lines.append(
                f"#{s.id:03d}  {s.dimensions_text}  ·  {s.area_m2:.3f} m²  ·  {thick}  ·  "
                f"{s.shape.label_es} ({s.regularity.label_es})  ·  {s.status.label_es}"
            )
        self._lbl_content.setText("\n".join(lines))

    # ─── Acciones ─────────────────────────────────────────────────────────────

    def _on_add_area(self) -> None:
        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Nuevo estante", "Nombre del estante:")
        if not ok or not name.strip():
            return
        self._storage_repo.save(StorageArea(name=name.strip()))
        self.reload()
        self.data_changed.emit()

    def _on_add_shelf(self) -> None:
        areas = self._storage_repo.get_all()
        if not areas:
            QMessageBox.information(
                self, "Sin estantes",
                "Cree primero un estante. La jerarquía es Estante → Repisa → Retal.",
            )
            return
        items = self._tree.selectedItems()
        area_id = None
        if items:
            kind, obj_id = items[0].data(0, Qt.ItemDataRole.UserRole)
            area_id = obj_id if kind == "area" else next(
                (s.storage_area_id for s in self._shelves if s.id == obj_id), None
            )
        if area_id is None:
            area_id = areas[0].id

        from PyQt6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(
            self, "Nueva repisa", f"Nombre de la repisa en «{next(a.display_name for a in areas if a.id == area_id)}»:"
        )
        if not ok or not name.strip():
            return
        self._shelf_repo.save(Shelf(
            storage_area_id=area_id, name=name.strip(), width_m=2.0, length_m=1.2
        ))
        self.reload()
        self.data_changed.emit()

    def _on_delete(self) -> None:
        items = self._tree.selectedItems()
        if not items:
            return
        kind, obj_id = items[0].data(0, Qt.ItemDataRole.UserRole)
        if kind == "shelf":
            shelf = next((s for s in self._shelves if s.id == obj_id), None)
            if shelf is None:
                return
            extra = ""
            if shelf.scrap_count:
                extra = (f"\n\nLa repisa contiene {shelf.scrap_count} retal(es): "
                         "quedarán SIN ubicación, pero no se borrarán.")
            reply = QMessageBox.question(
                self, "Confirmar",
                f"¿Eliminar «{shelf.location_text}»?{extra}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._shelf_repo.delete(shelf.id)
                self._current_shelf = None
                self.reload()
                self.data_changed.emit()
        else:
            area = self._storage_repo.get_by_id(obj_id)
            if area is None:
                return
            n = len([s for s in self._shelves if s.storage_area_id == obj_id])
            extra = (f"\n\nSe eliminarán también sus {n} repisa(s) y los retales "
                     "quedarán sin ubicación.") if n else ""
            reply = QMessageBox.question(
                self, "Confirmar",
                f"¿Eliminar «{area.display_name}»?{extra}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._storage_repo.delete(area.id)
                self.reload()
                self.data_changed.emit()

    def _on_save(self) -> None:
        if self._current_shelf is None:
            return
        name = self._in_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Nombre requerido", "La repisa necesita un nombre.")
            return

        if not (self._chk_regular.isChecked() or self._chk_irregular.isChecked()):
            QMessageBox.warning(
                self, "Reglas vacías",
                "La repisa debe admitir al menos una familia de formas, "
                "o ningún retal podrá asignarse nunca.",
            )
            return

        shelf = self._current_shelf
        shelf.name = name
        shelf.width_m = self._sp_width.value()
        shelf.length_m = self._sp_length.value()
        shelf.area_m2 = shelf.width_m * shelf.length_m
        shelf.rules = ShelfRules(
            accepts_regular=self._chk_regular.isChecked(),
            accepts_irregular=self._chk_irregular.isChecked(),
            min_width_m=_val(self._spin_min_w),
            max_width_m=_val(self._spin_max_w),
            min_length_m=_val(self._spin_min_l),
            max_length_m=_val(self._spin_max_l),
            min_area_m2=_val(self._spin_min_a),
            max_area_m2=_val(self._spin_max_a),
            min_thickness_mm=_val(self._spin_min_t),
            max_thickness_mm=_val(self._spin_max_t),
        )
        self._shelf_repo.update(shelf)
        self.reload()
        self._lbl_title.setText(shelf.location_text)
        self.data_changed.emit()

    def _on_export_dxf(self) -> None:
        if self._current_shelf is None:
            return
        if self._cad is None:
            QMessageBox.information(self, "Sin servicio CAD", "El servicio CAD no está disponible.")
            return
        try:
            path = self._cad.export_shelf(self._current_shelf)
        except CadExportError as exc:
            QMessageBox.critical(self, "Error al exportar", str(exc))
            return
        QMessageBox.information(
            self, "DXF generado",
            f"Plano de la repisa exportado:\n{path}\n\n"
            f"Dimensiones: {self._current_shelf.width_m:.2f} × "
            f"{self._current_shelf.length_m:.2f} m (en metros).",
        )
