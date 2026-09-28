"""
Gestión de temas dark / light para PyQt6.

Colores de categorías idénticos a la app Flutter para consistencia visual.
"""
from __future__ import annotations

from PyQt6.QtWidgets import QApplication

# ─── Colores de categoría (hex) — iguales que la app Flutter ──────────────────
CATEGORY_COLORS: dict[str, str] = {
    "A":     "#4caf50",
    "B":     "#2196f3",
    "C":     "#ff9800",
    "D":     "#ff5722",
    "error": "#f44336",
}

# ─── Colores de gestión de retales ───────────────────────────────────────────
# REUTILIZABLE / RECICLABLE coinciden con ScrapDestination.hex_color para que la
# lista de retales y el badge del diálogo hablen el mismo idioma visual.
DESTINATION_COLORS: dict[str, str] = {
    "REUTILIZABLE": "#4caf50",
    "RECICLABLE":   "#f44336",
}

# Semáforo de ocupación de repisa (verde / ámbar / rojo).
OCCUPANCY_COLORS: dict[str, str] = {
    "low":  "#4caf50",
    "mid":  "#ff9800",
    "high": "#f44336",
}

# Alerta de riesgo geométrico.
SAFETY_ALERT_COLOR: str = "#ff9800"

# ─── Tema oscuro ──────────────────────────────────────────────────────────────
DARK_QSS = """
/* Base */
QMainWindow, QDialog, QWidget {
    background-color: #1a1a2e;
    color: #e8e8f0;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}

/* Tabs */
QTabWidget::pane   { border: 1px solid #0f3460; background: #16213e; border-radius: 4px; }
QTabBar::tab       { background: #0f3460; color: #c0c0d0; padding: 9px 22px; border-radius: 4px 4px 0 0; min-width: 100px; }
QTabBar::tab:selected  { background: #e94560; color: #ffffff; font-weight: bold; }
QTabBar::tab:hover     { background: #1a4a8a; }

/* Botones */
QPushButton {
    background-color: #0f3460; color: #e8e8f0;
    border: none; padding: 8px 18px; border-radius: 6px; font-weight: bold;
}
QPushButton:hover    { background-color: #1a4a8a; }
QPushButton:pressed  { background-color: #e94560; color: #fff; }
QPushButton:disabled { background-color: #2a2a3e; color: #555568; }

QPushButton#btn_capture  { background: #e94560; font-size: 14px; padding: 10px 28px; }
QPushButton#btn_capture:hover { background: #ff6a7a; }
QPushButton#btn_calibrate { background: #0a7040; }
QPushButton#btn_calibrate:hover { background: #0d9050; }
QPushButton#btn_danger    { background: #8b1a1a; }
QPushButton#btn_danger:hover { background: #b02020; }
QPushButton#btn_secondary { background: #2a2a4a; }

/* Inputs */
QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #16213e; border: 1px solid #0f3460;
    border-radius: 4px; padding: 6px; color: #e8e8f0;
}
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #e94560; }
QComboBox::drop-down   { border: none; padding-right: 6px; }
QComboBox QAbstractItemView {
    background: #16213e; color: #e8e8f0;
    selection-background-color: #e94560;
}

/* Lista / tabla */
QListWidget, QTableWidget {
    background: #16213e; border: 1px solid #0f3460;
    border-radius: 6px; alternate-background-color: #1e2a4a;
}
QListWidget::item:hover, QTableWidget::item:hover { background: #0f3460; }
QListWidget::item:selected, QTableWidget::item:selected { background: #e94560; color: #fff; }
QHeaderView::section { background: #0f3460; color: #e8e8f0; padding: 6px; border: none; }

/* GroupBox */
QGroupBox {
    border: 1px solid #0f3460; border-radius: 6px;
    margin-top: 12px; padding: 8px 8px 8px 8px;
    font-weight: bold;
}
QGroupBox::title { color: #e94560; subcontrol-origin: margin; padding: 0 8px; }

/* ScrollBar */
QScrollBar:vertical   { background: #16213e; width: 10px; border-radius: 5px; }
QScrollBar::handle:vertical { background: #0f3460; border-radius: 5px; min-height: 24px; }
QScrollBar::handle:vertical:hover { background: #1a4a8a; }
QScrollBar:horizontal { background: #16213e; height: 10px; border-radius: 5px; }
QScrollBar::handle:horizontal { background: #0f3460; border-radius: 5px; min-width: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { height: 0; width: 0; }

/* Labels especiales */
QLabel#label_area    { font-size: 30px; font-weight: bold; color: #e8e8f0; }
QLabel#label_cat     { font-size: 18px; font-weight: bold; border-radius: 8px; padding: 4px 14px; }
QLabel#label_status  { font-size: 12px; color: #a0a0b8; }
QLabel#label_title   { font-size: 15px; font-weight: bold; color: #e94560; }

/* StatusBar */
QStatusBar          { background: #0f3460; color: #c0c0d0; border-top: 1px solid #e94560; }
QStatusBar::item    { border: none; }

/* Splitter */
QSplitter::handle   { background: #0f3460; }

/* CheckBox */
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 2px solid #0f3460; border-radius: 3px; background: #16213e; }
QCheckBox::indicator:checked { background: #e94560; border-color: #e94560; }

/* ToolTip */
QToolTip { background: #0f3460; color: #e8e8f0; border: 1px solid #e94560; padding: 4px; }

/* Árbol del almacén */
QTreeWidget { background: #16213e; border: 1px solid #0f3460; border-radius: 6px; }
QTreeWidget::item:selected, QTreeWidget::item:selected:active { background: #e94560; color: #fff; }
QTreeWidget::item:hover { background: #0f3460; }
QTreeView::branch { background: transparent; }

/* Barra de ocupación */
QProgressBar { background: #16213e; border: 1px solid #0f3460; border-radius: 5px; height: 18px; text-align: center; color: #e8e8f0; }
QProgressBar::chunk { background: #2196f3; border-radius: 4px; }
"""

# ─── Tema claro ───────────────────────────────────────────────────────────────
LIGHT_QSS = """
QMainWindow, QDialog, QWidget {
    background-color: #f4f6f9;
    color: #1a1a2e;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 13px;
}
QTabWidget::pane   { border: 1px solid #c0c8d8; background: #ffffff; border-radius: 4px; }
QTabBar::tab       { background: #dce3ec; color: #2a2a4a; padding: 9px 22px; border-radius: 4px 4px 0 0; min-width: 100px; }
QTabBar::tab:selected { background: #1565c0; color: #ffffff; font-weight: bold; }
QTabBar::tab:hover    { background: #c0cfe4; }

QPushButton {
    background: #1565c0; color: #ffffff;
    border: none; padding: 8px 18px; border-radius: 6px; font-weight: bold;
}
QPushButton:hover    { background: #1976d2; }
QPushButton:pressed  { background: #0d47a1; }
QPushButton:disabled { background: #c0c8d8; color: #808090; }
QPushButton#btn_capture  { background: #c62828; font-size: 14px; padding: 10px 28px; }
QPushButton#btn_capture:hover { background: #e53935; }
QPushButton#btn_calibrate { background: #1b5e20; }
QPushButton#btn_calibrate:hover { background: #2e7d32; }
QPushButton#btn_danger    { background: #b71c1c; }
QPushButton#btn_danger:hover { background: #d32f2f; }
QPushButton#btn_secondary { background: #90a4ae; color: #1a1a2e; }

QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    background: #ffffff; border: 1px solid #b0bec5;
    border-radius: 4px; padding: 6px; color: #1a1a2e;
}
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #1565c0; }
QComboBox QAbstractItemView {
    background: #ffffff; color: #1a1a2e;
    selection-background-color: #1565c0; selection-color: #fff;
}

QListWidget, QTableWidget {
    background: #ffffff; border: 1px solid #c0c8d8;
    border-radius: 6px; alternate-background-color: #f0f4f8;
}
QListWidget::item:hover, QTableWidget::item:hover { background: #e3f2fd; }
QListWidget::item:selected, QTableWidget::item:selected { background: #1565c0; color: #fff; }
QHeaderView::section { background: #dce3ec; color: #1a1a2e; padding: 6px; border: none; font-weight: bold; }

QGroupBox {
    border: 1px solid #c0c8d8; border-radius: 6px;
    margin-top: 12px; padding: 8px; font-weight: bold;
}
QGroupBox::title { color: #1565c0; subcontrol-origin: margin; padding: 0 8px; }

QScrollBar:vertical   { background: #f4f6f9; width: 10px; border-radius: 5px; }
QScrollBar::handle:vertical { background: #b0bec5; border-radius: 5px; min-height: 24px; }
QScrollBar:horizontal { background: #f4f6f9; height: 10px; border-radius: 5px; }
QScrollBar::handle:horizontal { background: #b0bec5; border-radius: 5px; min-width: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { height: 0; width: 0; }

QLabel#label_area   { font-size: 30px; font-weight: bold; color: #1a1a2e; }
QLabel#label_cat    { font-size: 18px; font-weight: bold; border-radius: 8px; padding: 4px 14px; }
QLabel#label_status { font-size: 12px; color: #607080; }
QLabel#label_title  { font-size: 15px; font-weight: bold; color: #1565c0; }

QTreeWidget { background: #ffffff; border: 1px solid #c0c8d8; border-radius: 6px; }
QTreeWidget::item:selected, QTreeWidget::item:selected:active { background: #1565c0; color: #fff; }
QTreeWidget::item:hover { background: #e3f2fd; }
QTreeView::branch { background: transparent; }

QProgressBar { background: #e0e6ed; border: 1px solid #b0bec5; border-radius: 5px; height: 18px; text-align: center; color: #1a1a2e; }
QProgressBar::chunk { background: #1565c0; border-radius: 4px; }

QStatusBar          { background: #dce3ec; color: #2a2a4a; border-top: 1px solid #b0bec5; }
QStatusBar::item    { border: none; }
QSplitter::handle   { background: #c0c8d8; }
QCheckBox::indicator { width: 16px; height: 16px; border: 2px solid #b0bec5; border-radius: 3px; background: #fff; }
QCheckBox::indicator:checked { background: #1565c0; border-color: #1565c0; }
QToolTip { background: #e8f0fe; color: #1a1a2e; border: 1px solid #1565c0; padding: 4px; }
"""


class ThemeManager:
    """Gestiona el tema visual dark/light de la aplicación."""

    def __init__(self) -> None:
        self._current: str = "dark"

    def apply(self, app: QApplication, theme: str) -> None:
        self._current = theme
        app.setStyleSheet(DARK_QSS if theme == "dark" else LIGHT_QSS)

    def toggle(self, app: QApplication) -> str:
        new_theme = "light" if self._current == "dark" else "dark"
        self.apply(app, new_theme)
        return new_theme

    @property
    def current_theme(self) -> str:
        return self._current
