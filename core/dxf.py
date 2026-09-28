"""
Exportación DXF de la geometría de un retal.

Flujo
-----
    Contorno OpenCV (miles de px)
         ↓  approxPolyDP  ← simplificación obligatoria
    Polilínea de 4-20 vértices
         ↓  escala px → mm  (raíz cuadrada del factorK)
    Geometría en milímetros
         ↓
    DXF (LWPOLYLINE cerrada, o CIRCLE si la pieza es un disco limpio)

Por qué la simplificación es obligatoria
----------------------------------------
Una máscara de 1280×720 produce un contorno de miles de puntos. Volcarlos tal
cual al DXF genera un archivo de varios MB que:
- tarda segundos en abrir en AutoCAD,
- reproduce cada artefacto de la segmentación como si fuera geometría real,
- es inútil como plano de corte.

La simplificación se hace con el MISMO polígono que usa la clasificación
geométrica (`core.geometry._contour_to_polygon`), de modo que lo que se ve en la
pantalla como "Rectángulo" es lo mismo que se abre en el CAD.

La tolerancia se expresa como fracción del perímetro (`simplify_ratio`), no como
píxeles absolutos, para que el resultado sea independiente de la resolución de la
cámara.

Sobre DWG
---------
No se intenta escribir DWG. Es un formato binario propietario y no hay librería
Python fiable y libre para escribirlo. DXF es el estándar de intercambio que
AutoCAD, BricsCAD, LibreCAD, QCAD y Fusion leen nativamente.
"""
from __future__ import annotations

import logging
import math
import os
from typing import Optional

import cv2
import numpy as np

from core.geometry import (
    _contour_to_polygon,
    _area_deficit,
    _side_lengths,
    CIRCLE_HULL_ERROR,
    CIRCLE_MIN_AREA_DEFICIT,
    CIRCULARITY_CIRCLE,
)

logger = logging.getLogger(__name__)

DEFAULT_SIMPLIFY_RATIO: float = 0.02
DEFAULT_DXF_VERSION: str = "R2010"

# Tolerancia (en unidades del dibujo) para considerar que dos puntos coinciden.
_WELD_TOLERANCE_MM: float = 0.01


def _find_center(contour: np.ndarray) -> Optional[tuple[float, float]]:
    """Centro del disco por momentos (independiente de la posición del origen)."""
    m = cv2.moments(contour)
    if abs(m["m00"]) < 1e-12:
        return None
    return (m["m10"] / m["m00"], m["m01"] / m["m00"])


def _looks_like_circle(contour: np.ndarray, poly: np.ndarray) -> Optional[tuple[float, float, float]]:
    """
    Decide si la geometría se puede representar limpiamente como un CIRCLE.

    Reutiliza exactamente los mismos tres criterios que `core.geometry` para no
    tener un "segundo clasificador" que se comporte distinto del que ve el
    usuario en pantalla: si la UI dice "Círculo", el DXF escribe un CIRCLE.

    Devuelve (cx, cy, radio_px) o None.
    """
    area = cv2.contourArea(contour)
    peri = cv2.arcLength(contour, True)
    if area <= 0 or peri <= 0:
        return None

    circularity = 4.0 * math.pi * area / (peri ** 2)
    if circularity < CIRCULARITY_CIRCLE:
        return None

    # Un hexágono tiene circularidad 0.82 y un cuadrado 0.785, pero el
    # hexágono pasa el umbral de 0.84... no, queda por debajo. Aun así el
    # déficit de área lo descarta de forma redundante y barata.
    hull_area = cv2.contourArea(cv2.convexHull(contour))
    if hull_area <= 0 or abs(area - hull_area) / hull_area > CIRCLE_HULL_ERROR:
        return None
    if _area_deficit(contour, poly) < CIRCLE_MIN_AREA_DEFICIT:
        return None

    center = _find_center(contour)
    if center is None:
        return None
    radius_px = math.sqrt(area / math.pi)
    if radius_px <= 0:
        return None
    return (center[0], center[1], radius_px)


def contour_to_dxf(
    contour: np.ndarray,
    factor_k: float,
    output_path: str,
    layer: str = "CONTORNO",
    simplify_ratio: float = DEFAULT_SIMPLIFY_RATIO,
    dxf_version: str = DEFAULT_DXF_VERSION,
) -> str:
    """
    Escribe la geometría de un contorno como archivo DXF.

    Args:
        contour:       Contorno Nx1x2 de OpenCV.
        factor_k:      FactorK vigente (m²/px²) para pasar px → mm.
        output_path:   Ruta completa del .dxf a escribir.
        layer:         Capa DXF donde se dibuja la geometría.
        simplify_ratio: ε de approxPolyDP como fracción del perímetro.
        dxf_version:   Versión del formato DXF (R12 es la más compatible).

    Returns:
        La ruta escrita.

    Raises:
        ValueError: Si el contorno es degenerado o factor_k es inválido.
        RuntimeError: Si ezdxf no está instalado o falla al escribir.
    """
    if contour is None or factor_k <= 0:
        raise ValueError("Contorno inválido o FactorK no positivo: no se puede exportar DXF.")

    area_px = cv2.contourArea(contour)
    if area_px <= 0:
        raise ValueError("El contorno tiene área cero: no se puede exportar DXF.")

    try:
        import ezdxf
    except ImportError as exc:  # pragma: no cover — depende del entorno
        raise RuntimeError(
            "La librería 'ezdxf' es necesaria para exportar a DXF.\n"
            "Instálela con:  pip install ezdxf"
        ) from exc

    # factor_k es m²/px² → su raíz da m/px → ×1000 convierte a mm/px.
    mm_per_px = math.sqrt(factor_k) * 1000.0

    doc = ezdxf.new(dxf_version)
    msp = doc.modelspace()
    if layer not in doc.layers:
        doc.layers.add(layer)

    poly = _contour_to_polygon(contour, simplify_ratio)

    circle = _looks_like_circle(contour, poly)
    if circle is not None:
        cx, cy, r_px = circle
        msp.add_circle(
            center=(cx * mm_per_px, cy * mm_per_px),
            radius=r_px * mm_per_px,
            dxfattribs={"layer": layer},
        )
        logger.info("DXF: geometría reconocida como círculo (r=%.1f mm)", r_px * mm_per_px)
    else:
        pts = [(float(x) * mm_per_px, float(y) * mm_per_px) for x, y in poly]
        msp.add_lwpolyline(
            pts,
            close=True,
            dxfattribs={"layer": layer},
        )
        logger.info("DXF: polilínea cerrada con %d vértices", len(pts))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    doc.saveas(output_path)
    logger.info("DXF exportado a %s", output_path)
    return output_path


def build_shelf_dxf(
    width_m: float,
    length_m: float,
    output_path: str,
    layer: str = "REPISA",
    dxf_version: str = DEFAULT_DXF_VERSION,
) -> str:
    """
    Genera el plano de una repisa vacía, en metros (no en mm).

    Es la representación que le interesa al usuario del almacén: un plano
    acotado de la superficie donde puede colocar los retales. Se usa metros
    porque así se superpone directamente sobre measurements drawings.
    """
    try:
        import ezdxf
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "La librería 'ezdxf' es necesaria para exportar a DXF. "
            "Instálela con:  pip install ezdxf"
        ) from exc

    if width_m <= 0 or length_m <= 0:
        raise ValueError("Las dimensiones de la repisa deben ser mayores que cero.")

    doc = ezdxf.new(dxf_version)
    msp = doc.modelspace()
    if layer not in doc.layers:
        doc.layers.add(layer)

    msp.add_lwpolyline(
        [(0.0, 0.0), (width_m, 0.0), (width_m, length_m), (0.0, length_m)],
        close=True,
        dxfattribs={"layer": layer},
    )

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    doc.saveas(output_path)
    logger.info("DXF de repisa exportado a %s (%0.2f × %0.2f m)", output_path, width_m, length_m)
    return output_path


def summarize_contour(contour: np.ndarray, factor_k: float) -> dict[str, float]:
    """
    Resumen numérico del contorno en unidades reales, para los tests y la UI.

    Devuelve área, perímetro y dimensiones del rectángulo mínimo rotado, todo
    ya convertido a metros mediante el FactorK.
    """
    if contour is None or factor_k <= 0:
        return {}
    mm_per_px = math.sqrt(factor_k) * 1000.0
    m_per_px = math.sqrt(factor_k)
    (_, (rw, rh), _) = cv2.minAreaRect(contour)
    return {
        "area_m2": cv2.contourArea(contour) * factor_k,
        "perimeter_m": cv2.arcLength(contour, True) * m_per_px,
        "length_m": max(rw, rh) * m_per_px,
        "width_m": min(rw, rh) * m_per_px,
        "perimeter_mm": cv2.arcLength(contour, True) * mm_per_px,
        "vertex_count": float(len(_side_lengths(_contour_to_polygon(contour, DEFAULT_SIMPLIFY_RATIO)))),
    }
