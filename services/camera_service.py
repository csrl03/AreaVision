"""
Servicio de cámara — Abstrae el acceso a webcam y cámara IP.

Soporta:
- Webcam por índice entero (0, 1, 2...)
- Cámara IP por URL RTSP o HTTP (validada antes de usarse)
"""
from __future__ import annotations

import logging
import re
from typing import Optional

import cv2
import numpy as np

from core.exceptions import CameraNotFoundError, CameraInitError, FrameCaptureError
from config import CAMERA_WIDTH, CAMERA_HEIGHT, CAMERA_FPS

logger = logging.getLogger(__name__)

# Regex para URLs de cámara IP — acepta rtsp://, http://, https://
_IP_URL_RE = re.compile(
    r"^(rtsp|http|https)://[a-zA-Z0-9.\-_]+(:\d{1,5})?(/[^\s]*)?$",
    re.IGNORECASE,
)


def validate_camera_url(url: str) -> bool:
    """Valida el formato de URL de cámara IP. No realiza conexión."""
    return bool(_IP_URL_RE.match(url.strip()))


def list_available_webcams(max_check: int = 6) -> list[int]:
    """Detecta los índices de webcam disponibles en el sistema (sin abrir stream)."""
    available = []
    for i in range(max_check):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)  # CAP_DSHOW más rápido en Windows
        if cap.isOpened():
            available.append(i)
        cap.release()
    return available


class CameraService:
    """
    Gestiona el ciclo de vida de la cámara y la lectura de frames.

    Uso:
        svc = CameraService()
        svc.open(0)           # Webcam
        svc.open("rtsp://...") # Cámara IP
        frame = svc.read_frame()
        svc.close()
    """

    def __init__(self) -> None:
        self._cap: Optional[cv2.VideoCapture] = None
        self._source: Optional[int | str] = None

    @property
    def is_open(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    @property
    def source(self) -> Optional[int | str]:
        return self._source

    def open(self, source: int | str) -> None:
        """
        Abre la cámara.

        Args:
            source: Índice entero (webcam) o URL string (cámara IP).

        Raises:
            CameraNotFoundError: Si la URL tiene formato inválido.
            CameraInitError: Si la cámara no se puede abrir.
        """
        if isinstance(source, str) and not validate_camera_url(source):
            raise CameraNotFoundError(
                f"URL de cámara IP inválida: '{source}'. "
                "Formato esperado: rtsp://host:puerto/ruta  o  http://host:puerto/video"
            )

        self.close()

        backend = cv2.CAP_DSHOW if isinstance(source, int) else cv2.CAP_ANY
        cap = cv2.VideoCapture(source, backend)

        if not cap.isOpened():
            raise CameraInitError(
                f"No se pudo abrir la cámara '{source}'. "
                "Verifique que esté conectada y no esté en uso por otra aplicación."
            )

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA_HEIGHT)
        cap.set(cv2.CAP_PROP_FPS, CAMERA_FPS)

        self._cap = cap
        self._source = source
        logger.info("Cámara abierta: %s", source)

    def read_frame(self) -> np.ndarray:
        """
        Lee un frame BGR de la cámara.

        Raises:
            FrameCaptureError: Si la cámara no está abierta o el frame falla.
        """
        if not self.is_open:
            raise FrameCaptureError("La cámara no está abierta. Llame a open() primero.")
        ret, frame = self._cap.read()
        if not ret or frame is None:
            raise FrameCaptureError("No se pudo leer el frame. El stream puede haber sido interrumpido.")
        return frame

    def close(self) -> None:
        """Libera la cámara."""
        if self._cap is not None:
            self._cap.release()
            self._cap = None
            logger.info("Cámara cerrada")

    def __enter__(self) -> CameraService:
        return self

    def __exit__(self, *_) -> None:
        self.close()
