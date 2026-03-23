"""
Ventana principal — QMainWindow con 3 pestañas: Cámara, Historial, Configuración.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QMainWindow, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QDoubleSpinBox, QSpinBox, QCheckBox, QListWidget,
    QListWidgetItem, QLineEdit, QComboBox, QGroupBox, QStatusBar,
    QMessageBox, QFileDialog, QSplitter, QGridLayout, QApplication,
    QFrame, QScrollArea,
)

from config import APP_TITLE, APP_VERSION, CAMERA_INDEX, WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT
from core.entities import Measurement, MeasurementCategory
from core.exceptions import (
    CameraError, CameraInitError, CalibrationNotFoundError, VisiSizeError,
)
from data.repositories import MeasurementRepository
from data.settings_repository import SettingsRepository, SENSITIVITY_PARAMS
from services.ai_classifier import ObjectClassifier
from services.calibration_service import CalibrationService
from services.camera_service import CameraService, list_available_webcams
from services.measurement_service import MeasurementService
from services.opencv_service import OpenCVService
from ui.theme import ThemeManager, CATEGORY_COLORS
from ui.widgets.camera_feed_widget import CameraFeedWidget
from ui.widgets.measurement_card import MeasurementCard

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Ventana principal con navegación por pestañas."""

    def __init__(
        self,
        camera_service: CameraService,
        measurement_service: MeasurementService,
        calibration_service: CalibrationService,
        measurement_repo: MeasurementRepository,
        theme_manager: ThemeManager,
        ai_classifier: ObjectClassifier,
        settings_repo: SettingsRepository,
        opencv_svc: OpenCVService,
    ) -> None:
        super().__init__()
        self._camera = camera_service
        self._measurement_svc = measurement_service
        self._calibration_svc = calibration_service
        self._repo = measurement_repo
        self._theme = theme_manager
        self._classifier = ai_classifier
        self._settings_repo = settings_repo
        self._opencv_svc = opencv_svc
        self._current_distance_cm: float = 50.0

        self.setWindowTitle(f"{APP_TITLE}  v{APP_VERSION}")
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.resize(WINDOW_MIN_WIDTH + 60, WINDOW_MIN_HEIGHT + 60)

        self._build_ui()
        self._update_status_bar()

    # ─── Construcción de UI ───────────────────────────────────────────────────

    def _build_ui(self) -> None:
        tabs = QTabWidget()
        tabs.addTab(self._build_camera_tab(), "  Cámara  ")
        tabs.addTab(self._build_history_tab(), "  Historial  ")
        tabs.addTab(self._build_settings_tab(), "  Configuración  ")
        tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(tabs)
        self._tabs = tabs

        # Barra de estado
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)

    # ── Pestaña Cámara ────────────────────────────────────────────────────────

    def _build_camera_tab(self) -> QWidget:
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Feed de cámara (expansible)
        self._feed = CameraFeedWidget(self._camera, self._measurement_svc)
        self._feed.captured.connect(self._on_frame_captured)
        layout.addWidget(self._feed, stretch=3)

        # Panel de control derecho
        ctrl_layout = QVBoxLayout()
        ctrl_layout.setSpacing(10)

        # ── Grupo Cámara ──
        cam_group = QGroupBox("Cámara")
        cam_lay = QVBoxLayout(cam_group)

        cam_row = QHBoxLayout()
        self._btn_start_cam = QPushButton("Iniciar cámara")
        self._btn_start_cam.setObjectName("btn_calibrate")
        self._btn_start_cam.clicked.connect(self._on_start_camera)
        cam_row.addWidget(self._btn_start_cam)

        self._btn_stop_cam = QPushButton("Detener")
        self._btn_stop_cam.setObjectName("btn_secondary")
        self._btn_stop_cam.clicked.connect(self._on_stop_camera)
        self._btn_stop_cam.setEnabled(False)
        cam_row.addWidget(self._btn_stop_cam)
        cam_lay.addLayout(cam_row)

        self._chk_detection = QCheckBox("Detección activa")
        self._chk_detection.setChecked(True)
        self._chk_detection.stateChanged.connect(self._on_toggle_detection)
        cam_lay.addWidget(self._chk_detection)

        ctrl_layout.addWidget(cam_group)

        # ── Grupo Distancia ──
        dist_group = QGroupBox("Distancia cámara-objeto")
        dist_lay = QVBoxLayout(dist_group)
        dist_lay.addWidget(QLabel("Distancia actual (cm):"))
        self._spin_distance = QDoubleSpinBox()
        self._spin_distance.setRange(1.0, 1000.0)
        self._spin_distance.setValue(50.0)
        self._spin_distance.setSingleStep(5.0)
        self._spin_distance.setSuffix("  cm")
        self._spin_distance.valueChanged.connect(self._on_distance_changed)
        dist_lay.addWidget(self._spin_distance)
        dist_lay.addWidget(
            QLabel("La corrección de distancia ajusta\nel FactorK automáticamente."),
        )
        ctrl_layout.addWidget(dist_group)

        # ── Botón Capturar ──
        self._btn_capture = QPushButton("  Capturar  ")
        self._btn_capture.setObjectName("btn_capture")
        self._btn_capture.clicked.connect(self._on_capture)
        self._btn_capture.setEnabled(False)
        ctrl_layout.addWidget(self._btn_capture)

        # ── Resultado Último Frame ──
        result_group = QGroupBox("Último resultado")
        result_lay = QVBoxLayout(result_group)

        self._lbl_area = QLabel("—")
        self._lbl_area.setObjectName("label_area")
        self._lbl_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        result_lay.addWidget(self._lbl_area)

        self._lbl_category = QLabel("—")
        self._lbl_category.setObjectName("label_cat")
        self._lbl_category.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_category.setStyleSheet("font-size: 16px; font-weight: bold; padding: 4px;")
        result_lay.addWidget(self._lbl_category)

        self._lbl_pixels = QLabel("")
        self._lbl_pixels.setObjectName("label_status")
        self._lbl_pixels.setAlignment(Qt.AlignmentFlag.AlignCenter)
        result_lay.addWidget(self._lbl_pixels)

        # Clasificación IA (placeholder hasta que el modelo esté listo)
        self._lbl_ai = QLabel("IA: sin modelo cargado")
        self._lbl_ai.setObjectName("label_status")
        self._lbl_ai.setAlignment(Qt.AlignmentFlag.AlignCenter)
        result_lay.addWidget(self._lbl_ai)

        ctrl_layout.addWidget(result_group)

        ctrl_layout.addStretch()

        # ── Calibrar ──
        self._btn_calibrate = QPushButton("Calibrar")
        self._btn_calibrate.setObjectName("btn_calibrate")
        self._btn_calibrate.clicked.connect(self._on_open_calibration)
        ctrl_layout.addWidget(self._btn_calibrate)

        ctrl_widget = QWidget()
        ctrl_widget.setLayout(ctrl_layout)
        ctrl_widget.setFixedWidth(260)
        layout.addWidget(ctrl_widget)

        return tab

    # ── Pestaña Historial ─────────────────────────────────────────────────────

    def _build_history_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Barra de búsqueda y filtros
        filter_row = QHBoxLayout()
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Buscar por nombre…")
        self._search_input.textChanged.connect(self._on_search_changed)
        filter_row.addWidget(self._search_input, stretch=2)

        self._filter_combo = QComboBox()
        self._filter_combo.addItem("Todas las categorías", None)
        for cat in MeasurementCategory:
            self._filter_combo.addItem(cat.label_es, cat)
        self._filter_combo.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._filter_combo, stretch=1)

        btn_export = QPushButton("Exportar CSV")
        btn_export.setObjectName("btn_secondary")
        btn_export.clicked.connect(self._on_export_csv)
        filter_row.addWidget(btn_export)

        btn_del_all = QPushButton("Eliminar todo")
        btn_del_all.setObjectName("btn_danger")
        btn_del_all.clicked.connect(self._on_delete_all)
        filter_row.addWidget(btn_del_all)

        layout.addLayout(filter_row)

        # Lista de mediciones
        self._list_widget = QListWidget()
        self._list_widget.setSpacing(2)
        self._list_widget.setAlternatingRowColors(True)
        self._list_widget.itemDoubleClicked.connect(self._on_measurement_double_clicked)
        layout.addWidget(self._list_widget)

        # Info pie
        self._lbl_count = QLabel("0 mediciones")
        self._lbl_count.setObjectName("label_status")
        layout.addWidget(self._lbl_count)

        return tab

    # ── Pestaña Configuración ─────────────────────────────────────────────────

    def _build_settings_tab(self) -> QWidget:
        # Contenedor exterior que contiene solo el scroll
        outer = QWidget()
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)

        # Área de scroll
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer_lay.addWidget(scroll)

        # Widget interior que contiene todos los grupos
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)
        scroll.setWidget(tab)

        # ── Grupo Cámara ──
        cam_grp = QGroupBox("Fuente de cámara")
        cam_lay = QGridLayout(cam_grp)
        cam_lay.setVerticalSpacing(10)
        cam_lay.setHorizontalSpacing(12)
        cam_lay.setContentsMargins(10, 12, 10, 12)

        cam_lay.addWidget(QLabel("Tipo:"), 0, 0)
        self._combo_cam_type = QComboBox()
        self._combo_cam_type.addItems(["Webcam (índice)", "Cámara IP (URL)"])
        self._combo_cam_type.currentIndexChanged.connect(self._on_cam_type_changed)
        cam_lay.addWidget(self._combo_cam_type, 0, 1)

        cam_lay.addWidget(QLabel("Índice:"), 1, 0)
        self._spin_cam_index = QDoubleSpinBox()
        self._spin_cam_index.setRange(0, 9)
        self._spin_cam_index.setDecimals(0)
        self._spin_cam_index.setValue(CAMERA_INDEX)
        cam_lay.addWidget(self._spin_cam_index, 1, 1)

        cam_lay.addWidget(QLabel("URL cámara IP:"), 2, 0)
        self._input_cam_url = QLineEdit()
        self._input_cam_url.setPlaceholderText("rtsp://192.168.1.10:554/stream")
        self._input_cam_url.setEnabled(False)
        cam_lay.addWidget(self._input_cam_url, 2, 1)

        btn_detect = QPushButton("Detectar webcams disponibles")
        btn_detect.clicked.connect(self._on_detect_webcams)
        cam_lay.addWidget(btn_detect, 3, 0, 1, 2)

        layout.addWidget(cam_grp)

        # ── Grupo Apariencia ──
        ui_grp = QGroupBox("Apariencia")
        ui_lay = QHBoxLayout(ui_grp)
        ui_lay.setContentsMargins(10, 12, 10, 12)
        ui_lay.setSpacing(12)
        ui_lay.addWidget(QLabel("Tema:"))
        self._combo_theme = QComboBox()
        self._combo_theme.addItems(["Oscuro", "Claro"])
        if self._theme.current_theme == "light":
            self._combo_theme.setCurrentIndex(1)
        self._combo_theme.currentIndexChanged.connect(self._on_theme_changed)
        ui_lay.addWidget(self._combo_theme)
        ui_lay.addStretch()
        layout.addWidget(ui_grp)

        # ── Grupo Calibración ──
        cal_grp = QGroupBox("Estado de calibración")
        cal_lay = QVBoxLayout(cal_grp)
        cal_lay.setContentsMargins(10, 12, 10, 12)
        cal_lay.setSpacing(10)
        self._lbl_cal_status = QLabel("Cargando…")
        cal_lay.addWidget(self._lbl_cal_status)
        btn_new_cal = QPushButton("Nueva calibración")
        btn_new_cal.setObjectName("btn_calibrate")
        btn_new_cal.clicked.connect(self._on_open_calibration)
        cal_lay.addWidget(btn_new_cal)
        layout.addWidget(cal_grp)

        # ── Grupo IA ──
        ai_grp = QGroupBox("Clasificador IA (Feature Futura)")
        ai_lay = QVBoxLayout(ai_grp)
        ai_lay.setContentsMargins(10, 12, 10, 12)
        ai_lay.setSpacing(8)
        ai_status = "Disponible" if self._classifier.is_available() else "Sin modelo cargado"
        ai_lay.addWidget(QLabel(f"Estado: {ai_status}"))
        ai_lay.addWidget(QLabel(f"Modelo: {self._classifier.model_name}"))
        ai_lay.addWidget(
            QLabel(
                "Para activar: entrenar modelo YOLOv8 y seguir\n"
                "las instrucciones en services/ai_classifier/yolo_classifier.py"
            )
        )
        layout.addWidget(ai_grp)

        # ── Grupo Detección de contornos ──────────────────────────────────────
        det_grp = QGroupBox("Detección de contornos")
        det_lay = QGridLayout(det_grp)
        det_lay.setVerticalSpacing(10)
        det_lay.setHorizontalSpacing(12)
        det_lay.setContentsMargins(10, 12, 10, 12)

        det_lay.addWidget(QLabel("Área mínima (px²):"), 0, 0)
        self._spin_min_pixels = QSpinBox()
        self._spin_min_pixels.setRange(1, 1_000_000)
        self._spin_min_pixels.setSingleStep(100)
        self._spin_min_pixels.setToolTip(
            "Contornos con menos píxeles que este valor son ignorados.\n"
            "Aumentar para descartar piezas muy pequeñas o ruido."
        )
        det_lay.addWidget(self._spin_min_pixels, 0, 1)

        det_lay.addWidget(QLabel("Sensibilidad:"), 1, 0)
        self._combo_sensitivity = QComboBox()
        self._combo_sensitivity.addItem("Alta  (más sensible, puede capturar sombras)", "alta")
        self._combo_sensitivity.addItem("Media  (recomendado)", "media")
        self._combo_sensitivity.addItem("Baja  (menos sensible, ignora detalles finos)", "baja")
        self._combo_sensitivity.setToolTip(
            "Controla cuán agresivo es el algoritmo al detectar bordes.\n"
            "Usa 'Baja' si se detectan sombras o líneas de la pared."
        )
        det_lay.addWidget(self._combo_sensitivity, 1, 1)

        btn_save_det = QPushButton("Aplicar y guardar detección")
        btn_save_det.clicked.connect(self._on_save_detection_settings)
        det_lay.addWidget(btn_save_det, 2, 0, 1, 2)
        layout.addWidget(det_grp)

        # ── Grupo Rangos de categorías ────────────────────────────────────────
        cat_grp = QGroupBox("Rangos de categorías (m²)")
        cat_lay = QGridLayout(cat_grp)
        cat_lay.setVerticalSpacing(10)
        cat_lay.setHorizontalSpacing(12)
        cat_lay.setContentsMargins(10, 12, 10, 12)
        cat_lay.addWidget(
            QLabel("Cada categoría va de su límite inferior al superior.\n"
                   "Los límites deben ser estrictamente ascendentes (A < B < C < D)."),
            0, 0, 1, 2,
        )

        cat_lay.addWidget(QLabel("Límite superior categoría A (m²):"), 1, 0)
        self._spin_cat_a = QDoubleSpinBox()
        self._spin_cat_a.setRange(0.01, 9_999.0)
        self._spin_cat_a.setDecimals(2)
        self._spin_cat_a.setSingleStep(0.5)
        cat_lay.addWidget(self._spin_cat_a, 1, 1)

        cat_lay.addWidget(QLabel("Límite superior categoría B (m²):"), 2, 0)
        self._spin_cat_b = QDoubleSpinBox()
        self._spin_cat_b.setRange(0.01, 9_999.0)
        self._spin_cat_b.setDecimals(2)
        self._spin_cat_b.setSingleStep(0.5)
        cat_lay.addWidget(self._spin_cat_b, 2, 1)

        cat_lay.addWidget(QLabel("Límite superior categoría C (m²):"), 3, 0)
        self._spin_cat_c = QDoubleSpinBox()
        self._spin_cat_c.setRange(0.01, 9_999.0)
        self._spin_cat_c.setDecimals(2)
        self._spin_cat_c.setSingleStep(0.5)
        cat_lay.addWidget(self._spin_cat_c, 3, 1)

        cat_lay.addWidget(QLabel("Límite superior categoría D (m²):"), 4, 0)
        self._spin_cat_d = QDoubleSpinBox()
        self._spin_cat_d.setRange(0.01, 9_999.0)
        self._spin_cat_d.setDecimals(2)
        self._spin_cat_d.setSingleStep(0.5)
        cat_lay.addWidget(self._spin_cat_d, 4, 1)

        cat_lay.addWidget(
            QLabel("Nota: áreas > D se clasifican como 'Fuera de rango'."), 5, 0, 1, 2
        )

        btn_save_cat = QPushButton("Aplicar y guardar categorías")
        btn_save_cat.clicked.connect(self._on_save_category_settings)
        cat_lay.addWidget(btn_save_cat, 6, 0, 1, 2)
        layout.addWidget(cat_grp)

        # Poblar controles con los valores actuales guardados
        self._load_settings_into_ui()

        layout.addStretch()
        return outer

    # ─── Slots — Cámara ───────────────────────────────────────────────────────

    def _on_start_camera(self) -> None:
        source: int | str
        if self._combo_cam_type.currentIndex() == 0:
            source = int(self._spin_cam_index.value())
        else:
            source = self._input_cam_url.text().strip()

        try:
            self._camera.open(source)
            self._feed.start_stream()
            self._btn_start_cam.setEnabled(False)
            self._btn_stop_cam.setEnabled(True)
            self._btn_capture.setEnabled(True)
            self._status_bar.showMessage(f"Cámara activa: {source}")
            logger.info("Cámara iniciada desde UI: %s", source)
        except CameraError as exc:
            QMessageBox.critical(self, "Error de cámara", str(exc))

    def _on_stop_camera(self) -> None:
        self._feed.stop_stream()
        self._camera.close()
        self._btn_start_cam.setEnabled(True)
        self._btn_stop_cam.setEnabled(False)
        self._btn_capture.setEnabled(False)
        self._feed.setText("Cámara detenida")
        self._feed.setPixmap(type(self._feed.pixmap())())
        self._status_bar.showMessage("Cámara detenida")

    def _on_toggle_detection(self, state: int) -> None:
        enabled = state == Qt.CheckState.Checked.value
        self._feed.set_detection_enabled(enabled)

    def _on_distance_changed(self, value: float) -> None:
        self._current_distance_cm = value
        self._feed.set_distance(value)

    def _on_capture(self) -> None:
        self._feed.capture_current_frame()

    def _on_frame_captured(
        self,
        frame,
        result,
        area_m2,
        category,
    ) -> None:
        """Recibe el frame capturado y muestra el diálogo de guardado."""
        # Actualizar labels de resultado en tiempo real (antes de guardar)
        if area_m2 is not None:
            self._lbl_area.setText(f"{area_m2:.4f} m²")
            cat_color = CATEGORY_COLORS.get(category.value if category else "error", "#9e9e9e")
            self._lbl_category.setText(category.label_es if category else "—")
            self._lbl_category.setStyleSheet(
                f"font-size: 16px; font-weight: bold; "
                f"background-color: {cat_color}; color: white; "
                f"border-radius: 6px; padding: 4px 10px;"
            )
        else:
            self._lbl_area.setText("Sin calibración")
            self._lbl_category.setText("—")

        if result and result.area_pixels:
            self._lbl_pixels.setText(f"{result.area_pixels:.0f} px²  ·  {result.processing_time_ms:.1f} ms")

        # Clasificación IA (si está disponible)
        cls_result = self._classifier.classify(frame) if self._classifier.is_available() else None
        if cls_result:
            self._lbl_ai.setText(f"IA: {cls_result.object_class} ({cls_result.confidence_pct})")

        if area_m2 is None:
            QMessageBox.warning(
                self, "Sin calibración",
                "No hay calibración disponible.\n"
                "Vaya a Configuración → Nueva calibración antes de medir."
            )
            return

        # Diálogo para guardar
        self._show_save_dialog(frame, result, area_m2, category)

    def _show_save_dialog(self, frame, result, area_m2, category) -> None:
        """Pregunta el nombre y guarda la medición."""
        from PyQt6.QtWidgets import QDialog, QDialogButtonBox
        dialog = QDialog(self)
        dialog.setWindowTitle("Guardar medición")
        dialog.setMinimumWidth(360)
        lay = QVBoxLayout(dialog)

        lay.addWidget(QLabel(f"Área medida: <b>{area_m2:.4f} m²</b>"))
        lay.addWidget(QLabel(f"Categoría:   <b>{category.label_es}</b>"))
        lay.addWidget(QLabel(f"Distancia:   <b>{self._current_distance_cm:.0f} cm</b>"))
        lay.addWidget(QLabel(""))
        lay.addWidget(QLabel("Nombre (opcional):"))
        name_input = QLineEdit()
        name_input.setPlaceholderText("Ej: Lámina sala 3")
        name_input.setMaxLength(120)
        lay.addWidget(name_input)

        lay.addWidget(QLabel("Notas (opcional):"))
        notes_input = QLineEdit()
        notes_input.setPlaceholderText("Descripción adicional…")
        notes_input.setMaxLength(250)
        lay.addWidget(notes_input)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(dialog.accept)
        btns.rejected.connect(dialog.reject)
        lay.addWidget(btns)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                m = self._measurement_svc.save_measurement(
                    processing_result=result,
                    area_m2=area_m2,
                    category=category,
                    distance_cm=self._current_distance_cm,
                    name=name_input.text().strip() or None,
                    notes=notes_input.text().strip() or None,
                )
                self._status_bar.showMessage(
                    f"Medición guardada (ID {m.id}): {m.area_m2:.4f} m²"
                )
                self._reload_history()
            except VisiSizeError as exc:
                QMessageBox.critical(self, "Error al guardar", str(exc))

    # ─── Slots — Historial ────────────────────────────────────────────────────

    def _reload_history(self, measurements: Optional[list] = None) -> None:
        if measurements is None:
            measurements = self._repo.get_all()
        self._list_widget.clear()
        for m in measurements:
            card = MeasurementCard(m)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, m.id)
            item.setSizeHint(card.sizeHint())
            self._list_widget.addItem(item)
            self._list_widget.setItemWidget(item, card)
        self._lbl_count.setText(f"{len(measurements)} medición(es)")

    def _on_search_changed(self, text: str) -> None:
        if text.strip():
            results = self._repo.search_by_name(text.strip())
        else:
            results = self._repo.get_all()
        self._reload_history(results)

    def _on_filter_changed(self, index: int) -> None:
        cat = self._filter_combo.itemData(index)
        if cat is None:
            self._reload_history()
        else:
            self._reload_history(self._repo.filter_by_category(cat))

    def _on_measurement_double_clicked(self, item: QListWidgetItem) -> None:
        m_id = item.data(Qt.ItemDataRole.UserRole)
        m = self._repo.get_by_id(m_id)
        if m:
            from ui.windows.measurement_detail_window import MeasurementDetailWindow
            win = MeasurementDetailWindow(m, parent=self)
            win.deleted.connect(self._on_measurement_deleted)
            win.exec()

    def _on_measurement_deleted(self, m_id: int) -> None:
        self._repo.delete(m_id)
        self._reload_history()
        self._status_bar.showMessage(f"Medición {m_id} eliminada")

    def _on_delete_all(self) -> None:
        count = self._list_widget.count()
        if count == 0:
            return
        reply = QMessageBox.question(
            self, "Confirmar",
            f"¿Eliminar las {count} mediciones del historial?\nEsta acción no se puede deshacer.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._repo.delete_all()
            self._reload_history()
            self._status_bar.showMessage("Historial eliminado")

    def _on_export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportar CSV", "mediciones.csv", "CSV (*.csv)"
        )
        if path:
            try:
                csv_data = self._repo.export_csv()
                with open(path, "w", encoding="utf-8") as f:
                    f.write(csv_data)
                self._status_bar.showMessage(f"CSV exportado: {path}")
            except Exception as exc:
                QMessageBox.critical(self, "Error al exportar", str(exc))

    # ─── Slots — Configuración ────────────────────────────────────────────────

    def _on_cam_type_changed(self, index: int) -> None:
        is_ip = index == 1
        self._input_cam_url.setEnabled(is_ip)
        self._spin_cam_index.setEnabled(not is_ip)

    def _on_detect_webcams(self) -> None:
        cams = list_available_webcams()
        if cams:
            QMessageBox.information(
                self, "Webcams detectadas",
                f"Índices disponibles: {', '.join(map(str, cams))}"
            )
        else:
            QMessageBox.warning(self, "Sin cámaras", "No se detectaron webcams.")

    def _on_theme_changed(self, index: int) -> None:
        theme = "light" if index == 1 else "dark"
        app = QApplication.instance()
        self._theme.apply(app, theme)

    def _on_open_calibration(self) -> None:
        if not self._camera.is_open:
            QMessageBox.warning(
                self, "Cámara inactiva",
                "Inicie la cámara primero (pestaña Cámara → Iniciar cámara).",
            )
            return
        from ui.windows.calibration_window import CalibrationWindow
        win = CalibrationWindow(
            camera=self._camera,
            calibration_svc=self._calibration_svc,
            parent=self,
        )
        if win.exec():
            self._update_status_bar()
            self._update_calibration_label()
            QMessageBox.information(self, "Calibración guardada", "Calibración guardada correctamente.")

    def _load_settings_into_ui(self) -> None:
        """Puebla los controles de configuración con los valores guardados en disco."""
        cfg = self._settings_repo.get()

        # Detección
        self._spin_min_pixels.setValue(cfg.get("min_contour_area_pixels", 500))
        sens = cfg.get("detection_sensitivity", "media")
        for i in range(self._combo_sensitivity.count()):
            if self._combo_sensitivity.itemData(i) == sens:
                self._combo_sensitivity.setCurrentIndex(i)
                break

        # Categorías
        thresholds = cfg.get("category_thresholds", {})
        self._spin_cat_a.setValue(thresholds.get("A", [0.0, 1.0])[1])
        self._spin_cat_b.setValue(thresholds.get("B", [1.0, 2.0])[1])
        self._spin_cat_c.setValue(thresholds.get("C", [2.0, 3.0])[1])
        self._spin_cat_d.setValue(thresholds.get("D", [3.0, 4.0])[1])

    def _on_save_detection_settings(self) -> None:
        """Valida, aplica y guarda la configuración de detección de contornos."""
        min_px = self._spin_min_pixels.value()
        sensitivity = self._combo_sensitivity.currentData()

        # QSpinBox garantiza entero ≥ 1 por su rango configurado, pero doble-verificamos
        if min_px < 1:
            QMessageBox.warning(self, "Valor inválido", "El área mínima debe ser al menos 1 px².")
            return

        cfg = dict(self._settings_repo.get())
        cfg["min_contour_area_pixels"] = min_px
        cfg["detection_sensitivity"] = sensitivity

        try:
            self._settings_repo.save(cfg)
        except OSError as exc:
            QMessageBox.critical(self, "Error al guardar", f"No se pudo guardar la configuración:\n{exc}")
            return

        # Aplicar en caliente al pipeline de visión
        sens_params = SENSITIVITY_PARAMS[sensitivity]
        self._opencv_svc.update_config(
            min_pixels=min_px,
            adaptive_c=sens_params["adaptive_c"],
            block_size=sens_params["block_size"],
        )
        QMessageBox.information(
            self, "Configuración guardada",
            f"Detección actualizada:\n"
            f"  Área mínima: {min_px} px²\n"
            f"  Sensibilidad: {sensitivity.capitalize()}"
        )

    def _on_save_category_settings(self) -> None:
        """Valida, aplica y guarda los rangos de categorías."""
        a_max = self._spin_cat_a.value()
        b_max = self._spin_cat_b.value()
        c_max = self._spin_cat_c.value()
        d_max = self._spin_cat_d.value()

        # Validación cruzada: límites deben ser estrictamente ascendentes
        if not (0 < a_max < b_max < c_max < d_max):
            QMessageBox.warning(
                self, "Valores inválidos",
                "Los límites de categorías deben ser estrictamente ascendentes:\n"
                "  0 < A < B < C < D\n\n"
                "Corrija los valores e intente nuevamente."
            )
            return

        new_thresholds = {
            "A": [0.0,   a_max],
            "B": [a_max, b_max],
            "C": [b_max, c_max],
            "D": [c_max, d_max],
        }

        cfg = dict(self._settings_repo.get())
        cfg["category_thresholds"] = new_thresholds

        try:
            self._settings_repo.save(cfg)
        except OSError as exc:
            QMessageBox.critical(self, "Error al guardar", f"No se pudo guardar la configuración:\n{exc}")
            return

        # Aplicar en caliente al clasificador
        from core.formulas import set_category_thresholds
        set_category_thresholds(new_thresholds)

        QMessageBox.information(
            self, "Categorías guardadas",
            f"Rangos actualizados:\n"
            f"  A: 0 – {a_max:.2f} m²\n"
            f"  B: {a_max:.2f} – {b_max:.2f} m²\n"
            f"  C: {b_max:.2f} – {c_max:.2f} m²\n"
            f"  D: {c_max:.2f} – {d_max:.2f} m²\n"
            f"  Fuera de rango: > {d_max:.2f} m²"
        )

    # ─── Ciclo de vida ────────────────────────────────────────────────────────

    def _on_tab_changed(self, index: int) -> None:
        if index == 1:   # Historial
            self._reload_history()
        elif index == 2:  # Configuración
            self._update_calibration_label()

    def _update_status_bar(self) -> None:
        if self._calibration_svc.has_calibration():
            cal = self._calibration_svc.load()
            age = cal.age_days
            warning = "  ⚠ Calibración antigua" if age > 30 else ""
            self._status_bar.showMessage(
                f"Calibrado  ·  factorK={cal.factor_k:.3e}  ·  "
                f"distancia={cal.calibration_distance_cm:.0f} cm  ·  "
                f"hace {age} días{warning}"
            )
        else:
            self._status_bar.showMessage("Sin calibración — vaya a Configuración → Nueva calibración")

    def _update_calibration_label(self) -> None:
        if hasattr(self, "_lbl_cal_status"):
            if self._calibration_svc.has_calibration():
                cal = self._calibration_svc.load()
                self._lbl_cal_status.setText(
                    f"✓ Calibrado  ·  {cal.calibration_date.strftime('%d/%m/%Y')}\n"
                    f"FactorK: {cal.factor_k:.4e}\n"
                    f"Distancia de calibración: {cal.calibration_distance_cm:.0f} cm\n"
                    f"Resolución: {cal.calibration_image_width}×{cal.calibration_image_height}"
                )
            else:
                self._lbl_cal_status.setText("✗ Sin calibración")

    def closeEvent(self, event: QCloseEvent) -> None:
        self._feed.stop_stream()
        self._camera.close()
        logger.info("Aplicación cerrada")
        event.accept()
