"""
Ventana de calibración — Asistente paso a paso con QDialog.

Pasos:
  1. Capturar un frame de la cámara
  2. Dibujar rectángulo sobre el objeto de referencia
  3. Ingresar área real (m²) y distancia (cm)
  4. Previsualizar el FactorK calculado
  5. Guardar
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QDoubleSpinBox, QGroupBox, QStackedWidget, QWidget,
    QLineEdit, QMessageBox, QFrame,
)

from core.entities import CalibrationData
from core.exceptions import CalibrationValidationError, CameraError
from services.calibration_service import CalibrationService
from services.camera_service import CameraService

logger = logging.getLogger(__name__)


class CalibrationWindow(QDialog):
    """
    Diálogo de calibración guiado en 3 pasos.
    Retorna QDialog.Accepted cuando la calibración fue guardada.
    """

    def __init__(
        self,
        camera: CameraService,
        calibration_svc: CalibrationService,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Nueva calibración")
        self.setMinimumSize(680, 560)
        self.setModal(True)

        self._camera = camera
        self._cal_svc = calibration_svc
        self._captured_frame: Optional[np.ndarray] = None
        self._calculated_cal: Optional[CalibrationData] = None

        self._build_ui()

    # ─── Construcción ─────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        main_lay = QVBoxLayout(self)
        main_lay.setContentsMargins(16, 16, 16, 16)
        main_lay.setSpacing(12)

        # Título y número de paso
        self._lbl_step = QLabel("Paso 1 de 3 — Capturar imagen de referencia")
        self._lbl_step.setObjectName("label_title")
        main_lay.addWidget(self._lbl_step)

        # Separador
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        main_lay.addWidget(sep)

        # Contenido por pasos
        self._stack = QStackedWidget()
        self._stack.addWidget(self._build_step1())
        self._stack.addWidget(self._build_step2())
        self._stack.addWidget(self._build_step3())
        main_lay.addWidget(self._stack, stretch=1)

        # Navegación
        nav = QHBoxLayout()
        self._btn_back = QPushButton("← Atrás")
        self._btn_back.setObjectName("btn_secondary")
        self._btn_back.clicked.connect(self._go_back)
        self._btn_back.setEnabled(False)
        nav.addWidget(self._btn_back)
        nav.addStretch()
        self._btn_next = QPushButton("Capturar frame  →")
        self._btn_next.setObjectName("btn_calibrate")
        self._btn_next.clicked.connect(self._go_next)
        nav.addWidget(self._btn_next)
        main_lay.addLayout(nav)

    # ── Paso 1: Capturar frame ────────────────────────────────────────────────

    def _build_step1(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(10)
        lay.addWidget(QLabel(
            "Coloca sobre la cámara un objeto de <b>área conocida</b> en m².\n"
            "Ejemplo: una hoja A4 (0.0623 m²), una baldosa 30×30 cm (0.09 m²).\n\n"
            "Asegúrate de que el objeto llene una parte visible de la imagen\n"
            "y que esté bien iluminado."
        ))
        self._lbl_preview1 = QLabel("Presiona 'Capturar frame' para congelar la imagen.")
        self._lbl_preview1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_preview1.setMinimumHeight(200)
        self._lbl_preview1.setStyleSheet("background: #0a0a18; border-radius: 6px;")
        lay.addWidget(self._lbl_preview1, stretch=1)
        lay.addStretch()
        return w

    # ── Paso 2: Seleccionar área ───────────────────────────────────────────────

    def _build_step2(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(8)
        lay.addWidget(QLabel(
            "Dibuja un <b>rectángulo</b> alrededor del objeto de referencia.\n"
            "Mantén presionado y arrastra para definir el área."
        ))
        from ui.widgets.area_selector_widget import AreaSelectorWidget
        self._area_selector = AreaSelectorWidget()
        self._area_selector.area_selected.connect(self._on_area_selected)
        lay.addWidget(self._area_selector, stretch=1)
        self._lbl_selected_px = QLabel("Área seleccionada: —")
        self._lbl_selected_px.setObjectName("label_status")
        lay.addWidget(self._lbl_selected_px)
        return w

    # ── Paso 3: Ingresar valores conocidos ────────────────────────────────────

    def _build_step3(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setSpacing(12)
        lay.addWidget(QLabel(
            "Ingresa el <b>área real</b> del objeto de referencia\n"
            "y la <b>distancia</b> entre la cámara y el objeto."
        ))

        grp = QGroupBox("Datos de referencia")
        grp_lay = QVBoxLayout(grp)

        row_area = QHBoxLayout()
        row_area.addWidget(QLabel("Área real del objeto (m²):"))
        self._spin_known_area = QDoubleSpinBox()
        self._spin_known_area.setRange(0.0001, 100.0)
        self._spin_known_area.setDecimals(4)
        self._spin_known_area.setValue(0.0623)  # Hoja A4 por defecto
        self._spin_known_area.setSingleStep(0.01)
        row_area.addWidget(self._spin_known_area)
        grp_lay.addLayout(row_area)

        row_dist = QHBoxLayout()
        row_dist.addWidget(QLabel("Distancia cámara-objeto (cm):"))
        self._spin_cal_distance = QDoubleSpinBox()
        self._spin_cal_distance.setRange(1.0, 1000.0)
        self._spin_cal_distance.setDecimals(1)
        self._spin_cal_distance.setValue(50.0)
        self._spin_cal_distance.setSingleStep(5.0)
        row_dist.addWidget(self._spin_cal_distance)
        grp_lay.addLayout(row_dist)

        row_notes = QHBoxLayout()
        row_notes.addWidget(QLabel("Notas (opcional):"))
        self._input_notes = QLineEdit()
        self._input_notes.setPlaceholderText("Ej: Hoja A4, luz natural")
        self._input_notes.setMaxLength(200)
        row_notes.addWidget(self._input_notes)
        grp_lay.addLayout(row_notes)

        lay.addWidget(grp)

        # Previsualización del resultado
        self._lbl_cal_preview = QLabel("Completa los datos y presiona 'Calcular'.")
        self._lbl_cal_preview.setObjectName("label_status")
        self._lbl_cal_preview.setWordWrap(True)
        lay.addWidget(self._lbl_cal_preview)

        # Botón calcular
        btn_calc = QPushButton("Calcular FactorK")
        btn_calc.clicked.connect(self._on_calculate)
        lay.addWidget(btn_calc)

        lay.addStretch()
        return w

    # ─── Navegación ───────────────────────────────────────────────────────────

    def _go_next(self) -> None:
        step = self._stack.currentIndex()

        if step == 0:  # Paso 1 → capturar frame
            try:
                frame = self._camera.read_frame()
                self._captured_frame = frame
                # Mostrar miniatura en step1
                self._show_preview_step1(frame)
                # Cargar frame en el selector
                self._area_selector.set_frame(frame)
                self._stack.setCurrentIndex(1)
                self._lbl_step.setText("Paso 2 de 3 — Seleccionar área del objeto")
                self._btn_back.setEnabled(True)
                self._btn_next.setText("Continuar  →")
                self._btn_next.setEnabled(False)  # Hasta que se haga selección
            except CameraError as exc:
                QMessageBox.critical(self, "Error de cámara", str(exc))

        elif step == 1:  # Paso 2 → continuar si hay selección
            if not self._area_selector.has_selection:
                QMessageBox.warning(
                    self, "Sin selección",
                    "Dibuja un rectángulo alrededor del objeto de referencia."
                )
                return
            self._stack.setCurrentIndex(2)
            self._lbl_step.setText("Paso 3 de 3 — Ingresar área real y distancia")
            self._btn_next.setText("Guardar calibración")
            self._btn_next.setEnabled(True)

        elif step == 2:  # Paso 3 → guardar
            self._on_save()

    def _go_back(self) -> None:
        step = self._stack.currentIndex()
        if step == 1:
            self._stack.setCurrentIndex(0)
            self._lbl_step.setText("Paso 1 de 3 — Capturar imagen de referencia")
            self._btn_back.setEnabled(False)
            self._btn_next.setText("Capturar frame  →")
            self._btn_next.setEnabled(True)
        elif step == 2:
            self._stack.setCurrentIndex(1)
            self._lbl_step.setText("Paso 2 de 3 — Seleccionar área del objeto")
            self._btn_next.setText("Continuar  →")
            self._btn_next.setEnabled(self._area_selector.has_selection)

    # ─── Slots ────────────────────────────────────────────────────────────────

    def _on_area_selected(self, area_px: float, _rect) -> None:
        self._lbl_selected_px.setText(f"Área seleccionada: {area_px:.0f} px²")
        self._btn_next.setEnabled(True)

    def _on_calculate(self) -> None:
        if not self._area_selector.has_selection or self._captured_frame is None:
            return
        try:
            h, w = self._captured_frame.shape[:2]
            cal = self._cal_svc.calculate(
                area_pixels=self._area_selector.confirmed_area_pixels,
                known_area_m2=self._spin_known_area.value(),
                image_width=w,
                image_height=h,
                distance_cm=self._spin_cal_distance.value(),
                notes=self._input_notes.text().strip() or None,
            )
            self._calculated_cal = cal
            self._lbl_cal_preview.setText(
                f"<b>FactorK calculado:</b>  {cal.factor_k:.4e} m²/px²\n"
                f"Distancia de calibración: {cal.calibration_distance_cm:.1f} cm\n"
                f"Área referencia: {cal.calibration_area_pixels:.0f} px²  ≡  "
                f"{cal.calibration_area_real_m2:.4f} m²\n"
                f"Resolución: {w}×{h}\n\n"
                "Presiona 'Guardar calibración' para confirmar."
            )
        except CalibrationValidationError as exc:
            QMessageBox.warning(self, "Datos inválidos", str(exc))

    def _on_save(self) -> None:
        if self._calculated_cal is None:
            self._on_calculate()
            if self._calculated_cal is None:
                return
        try:
            self._cal_svc.save(self._calculated_cal)
            self.accept()
        except Exception as exc:
            QMessageBox.critical(self, "Error al guardar", str(exc))

    # ─── Auxiliares ───────────────────────────────────────────────────────────

    def _show_preview_step1(self, frame: np.ndarray) -> None:
        import cv2
        from PyQt6.QtGui import QImage, QPixmap
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qt_img = QImage(rgb.tobytes(), w, h, w * ch, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(qt_img).scaled(
            self._lbl_preview1.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._lbl_preview1.setPixmap(pix)
