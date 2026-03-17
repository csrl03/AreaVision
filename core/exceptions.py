"""
Jerarquía de errores tipados de VisiSize.

Todos los errores del dominio heredan de VisiSizeError para poder ser
capturados de forma selectiva en los bloques try/except de la UI.
"""


class VisiSizeError(Exception):
    """Base de todos los errores internos de VisiSize."""


# ─── Cámara ────────────────────────────────────────────────────────────────────

class CameraError(VisiSizeError):
    """Error genérico de cámara."""


class CameraNotFoundError(CameraError):
    """No se encontró ninguna cámara con el índice o URL dados."""


class CameraInitError(CameraError):
    """La cámara no pudo abrirse dentro del tiempo límite."""


class FrameCaptureError(CameraError):
    """Fallo al leer un frame de la cámara (stream interrumpido)."""


# ─── Procesamiento de imagen ──────────────────────────────────────────────────

class ProcessingError(VisiSizeError):
    """Error durante el pipeline OpenCV."""


class NoContourFoundError(ProcessingError):
    """No se detectó ningún contorno válido en la imagen."""


# ─── Calibración ──────────────────────────────────────────────────────────────

class CalibrationError(VisiSizeError):
    """Error genérico de calibración."""


class CalibrationNotFoundError(CalibrationError):
    """No hay datos de calibración guardados."""


class CalibrationValidationError(CalibrationError):
    """Los datos de calibración son inválidos (FactorK fuera de rango, área insuficiente, etc.)."""


# ─── Almacenamiento ───────────────────────────────────────────────────────────

class StorageError(VisiSizeError):
    """Error de acceso a base de datos o sistema de archivos."""
