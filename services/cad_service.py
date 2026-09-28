"""
Servicio de exportación CAD (DXF).

Fachada de aplicación sobre `core.dxf`. Existe para tres cosas:

1. **Rutas seguras.** Los nombres de archivo se generan a partir del id y del
   timestamp, nunca de texto que el usuario haya escrito. Es la misma defensa
   que usa `ImageStorageService` contra path traversal.
2. **Reconstruir la geometría desde el inventario.** Un retal guardado solo
   tiene dimensiones; para dibujar su contorno real hay que volver a la imagen.
   `export_from_silhouette` recupera el contorno desde el PNG guardado.
3. **Un solo sitio donde la UI llama.** La UI no importa `core.dxf` ni `ezdxf`
   directamente: habla con este servicio y recibe rutas o excepciones tipadas.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime
from typing import Optional

import cv2
import numpy as np

from config import DATA_DIR
from core.dxf import build_shelf_dxf, contour_to_dxf, summarize_contour
from core.entities import Scrap, Shelf
from core.exceptions import VisiSizeError

logger = logging.getLogger(__name__)

DEFAULT_DXF_DIR: str = os.path.join(DATA_DIR, "dxf")
DEFAULT_SIMPLIFY_RATIO: float = 0.02

# Caracteres que se eliminan de los nombres de archivo generados.
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


class CadExportError(VisiSizeError):
    """No se pudo generar el archivo DXF."""


class CadService:
    """Genera planos DXF de retales y de repisas."""

    def __init__(
        self,
        output_dir: str = DEFAULT_DXF_DIR,
        simplify_ratio: float = DEFAULT_SIMPLIFY_RATIO,
    ) -> None:
        self._dir = output_dir
        self._simplify_ratio = simplify_ratio
        os.makedirs(self._dir, exist_ok=True)

    def set_simplify_ratio(self, ratio: float) -> None:
        """Ajusta la tolerancia de simplificación (fracción del perímetro)."""
        if 0.0 < ratio <= 0.2:
            self._simplify_ratio = float(ratio)

    @property
    def output_dir(self) -> str:
        return self._dir

    # ─── Retales ──────────────────────────────────────────────────────────────

    def export_contour(
        self,
        contour: np.ndarray,
        factor_k: float,
        scrap: Optional[Scrap] = None,
        filename: Optional[str] = None,
    ) -> str:
        """
        Exporta el contorno de un retal a DXF.

        Args:
            contour:   Contorno Nx1x2 de OpenCV.
            factor_k:  FactorK vigente (m²/px²) para el escalado px → mm.
            scrap:     Retal asociado; solo se usa para nombrar el archivo.
            filename:  Nombre explícito; si se omite se genera uno seguro.

        Returns:
            Ruta del archivo .dxf escrito.

        Raises:
            CadExportError: Si el contorno es inválido o ezdxf falla.
        """
        if contour is None:
            raise CadExportError("No hay contorno disponible para exportar.")

        path = os.path.join(self._dir, filename or self._build_filename(scrap, "RETAL"))
        try:
            return contour_to_dxf(
                contour,
                factor_k,
                path,
                simplify_ratio=self._simplify_ratio,
            )
        except ValueError as exc:
            raise CadExportError(str(exc)) from exc
        except Exception as exc:
            raise CadExportError(f"Error al escribir el DXF: {exc}") from exc

    def export_from_silhouette(
        self,
        silhouette_path: Optional[str],
        factor_k: float,
        scrap: Optional[Scrap] = None,
        filename: Optional[str] = None,
    ) -> str:
        """
        Exporta a DXF reconstruyendo el contorno desde la silueta guardada.

        La silueta que guarda `ImageStorageService` es la imagen con el overlay
        del pipeline. Si el rectángulo del contorno es detectables, se recupera;
        si no, se cae al rectángulo mínimo de la silueta, que es una aproximación
        que debe quedar indicada en el log.

        Returns:
            Ruta del archivo .dxf escrito.

        Raises:
            CadExportError: Si la imagen no existe o no se puede leer.
        """
        if not silhouette_path or not os.path.exists(silhouette_path):
            raise CadExportError(
                "Este retal no tiene imagen de silueta guardada; "
                "no se puede reconstruir su contorno."
            )
        try:
            img = cv2.imread(silhouette_path, cv2.IMREAD_GRAYSCALE)
        except Exception as exc:
            raise CadExportError(f"No se pudo leer la silueta: {exc}") from exc
        if img is None:
            raise CadExportError("La silueta está dañada o no es una imagen válida.")

        contour = self._contour_from_silhouette(img)
        if contour is None:
            raise CadExportError("No se pudo extraer un contorno de la silueta guardada.")
        return self.export_contour(contour, factor_k, scrap, filename)

    def export_scrap_rectangle(
        self,
        scrap: Scrap,
        filename: Optional[str] = None,
    ) -> str:
        """
        Exporta el rectángulo mínimo del retal usando sus dimensiones guardadas.

        Es el plano de respaldo cuando no hay imagen: dibuja el
        `width_m × length_m` del inventario, que es la geometría que el sistema
        conoce con certeza. No inventa el contorno real.
        """
        if scrap is None or scrap.width_m <= 0 or scrap.length_m <= 0:
            raise CadExportError("El retal no tiene dimensiones válidas para exportar.")
        try:
            import ezdxf
        except ImportError as exc:
            raise CadExportError(
                "La librería 'ezdxf' es necesaria para exportar a DXF. "
                "Instálela con:  pip install ezdxf"
            ) from exc

        path = os.path.join(self._dir, filename or self._build_filename(scrap, "RETAL"))
        doc = ezdxf.new("R2010")
        msp = doc.modelspace()
        if "CONTORNO" not in doc.layers:
            doc.layers.add("CONTORNO")
        w, h = scrap.length_m, scrap.width_m
        msp.add_lwpolyline(
            [(0.0, 0.0), (w, 0.0), (w, h), (0.0, h)],
            close=True,
            dxfattribs={"layer": "CONTORNO"},
        )
        os.makedirs(self._dir, exist_ok=True)
        doc.saveas(path)
        logger.info("DXF de rectángulo de retal exportado a %s", path)
        return path

    # ─── Repisas ──────────────────────────────────────────────────────────────

    def export_shelf(self, shelf: Shelf, filename: Optional[str] = None) -> str:
        """Exporta el plano de una repisa vacía, en metros."""
        if shelf is None or shelf.width_m <= 0 or shelf.length_m <= 0:
            raise CadExportError("La repisa no tiene dimensiones válidas para exportar.")
        name = filename or f"REPISA_{shelf.id or 0}_{_slug(shelf.name)}_{datetime.now():%Y%m%d_%H%M%S_%f}.dxf"
        try:
            return build_shelf_dxf(shelf.width_m, shelf.length_m, os.path.join(self._dir, name))
        except Exception as exc:
            raise CadExportError(f"Error al escribir el DXF de la repisa: {exc}") from exc

    # ─── Interno ──────────────────────────────────────────────────────────────

    def _build_filename(self, scrap: Optional[Scrap], prefix: str) -> str:
        """
        Nombre de archivo seguro, derivado solo de id + timestamp.

        Nunca del texto del usuario: un retal llamado "../../evil" no puede
        escapar del directorio de salida.

        Incluye microsegundos porque dos exportaciones del mismo retal dentro
        del mismo segundo son habituales (contorno real y rectángulo de
        respaldo) y con resolución de segundo la segunda sobrescribiría la
        primera.
        """
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        if scrap is not None and scrap.id is not None:
            return f"{prefix}_{scrap.id:03d}_{stamp}.dxf"
        return f"{prefix}_{stamp}.dxf"

    @staticmethod
    def _contour_from_silhouette(img: np.ndarray) -> Optional[np.ndarray]:
        """
        Extrae el contorno principal de una silueta guardada.

        Aplica el mismo criterio de selección que el pipeline en vivo (área
        máxima, solidez mínima) para no devolver un fragmento de overlay.
        """
        blur = cv2.GaussianBlur(img, (5, 5), 0)
        _, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        total = img.shape[0] * img.shape[1]
        min_area = max(total * 0.001, 500.0)
        max_area = total * 0.95

        valid = []
        for c in contours:
            area = cv2.contourArea(c)
            hull = cv2.contourArea(cv2.convexHull(c))
            solidity = area / hull if hull > 0 else 0.0
            if min_area < area < max_area and solidity >= 0.60:
                valid.append(c)

        if not valid:
            logger.warning(
                "Ningún contorno de la silueta superó el filtro; se usa el mayor disponible."
            )
            return max(contours, key=cv2.contourArea)
        return max(valid, key=cv2.contourArea)

    @staticmethod
    def summarize(scrap: Scrap) -> dict:
        """Métricas descriptivas de un retal, para la ficha de inventario."""
        return {
            "area_m2": scrap.area_m2,
            "length_m": scrap.length_m,
            "width_m": scrap.width_m,
            "perimeter_m": 2.0 * (scrap.length_m + scrap.width_m),
            "vertex_count": float(scrap.vertex_count or 0),
        }


def _slug(text: Optional[str]) -> str:
    """Convierte texto libre en un fragmento de nombre de archivo seguro."""
    if not text:
        return "sin_nombre"
    cleaned = _UNSAFE_CHARS.sub("_", text).strip("_.")
    return cleaned[:40] or "sin_nombre"


__all__ = ["CadService", "CadExportError", "summarize_contour", "build_shelf_dxf", "contour_to_dxf"]
