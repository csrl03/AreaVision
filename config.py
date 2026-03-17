"""
VisiSize Python — Configuración Global
=======================================
Modifica este archivo para ajustar el comportamiento de la aplicación.
Los parámetros de algoritmo (OpenCV, umbrales de categoría) están en core/constants.py.
"""

import os

# ─── Cámara ────────────────────────────────────────────────────────────────────
CAMERA_INDEX: int = 0
# URL de cámara IP. Ejemplo: "rtsp://192.168.1.10:554/stream" o "http://192.168.1.10:8080/video"
CAMERA_IP_URL: str = ""
CAMERA_WIDTH: int = 1280
CAMERA_HEIGHT: int = 720
CAMERA_FPS: int = 30

# ─── Rutas de datos ────────────────────────────────────────────────────────────
BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
DATA_DIR: str = os.path.join(BASE_DIR, "data")
DB_PATH: str = os.path.join(DATA_DIR, "measurements.db")
IMAGES_DIR: str = os.path.join(DATA_DIR, "images")
CALIBRATION_PATH: str = os.path.join(DATA_DIR, "calibration.json")

# ─── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL: str = "INFO"
LOG_FILE: str = os.path.join(BASE_DIR, "app.log")

# ─── UI ────────────────────────────────────────────────────────────────────────
APP_TITLE: str = "VisiSize"
APP_VERSION: str = "1.0.0"
# Tema por defecto: "dark" o "light"
DEFAULT_THEME: str = "dark"
WINDOW_MIN_WIDTH: int = 1180
WINDOW_MIN_HEIGHT: int = 740
