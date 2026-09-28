"""
Fixtures compartidas de la suite de pruebas.

Las piezas de prueba se generan sintéticamente con OpenCV, de modo que las
pruebas no dependen de una cámara ni de fotografías reales: son formas
conocidas con dimensiones esperadas.
"""
from __future__ import annotations

import math
import os
import sys

import cv2
import numpy as np
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# FactorK de referencia: 0.0001 m²/px²  →  10 px = 0.01 m  →  1 px = 1 cm
FACTOR_K = 0.0001
PX_TO_M = math.sqrt(FACTOR_K)   # 0.01 m/px


def contour_from_mask(mask: np.ndarray) -> np.ndarray:
    """Devuelve el contorno externo más grande de una máscara binaria."""
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    assert contours, "La máscara no produjo contornos"
    return max(contours, key=cv2.contourArea)


def rect_contour(w_px: float, h_px: float, canvas: int = 800) -> np.ndarray:
    """Rectángulo de w_px × h_px con la esquina superior izquierda en (100, 100)."""
    mask = np.zeros((canvas, canvas), np.uint8)
    cv2.rectangle(
        mask, (100, 100), (int(100 + w_px), int(100 + h_px)), 255, thickness=-1
    )
    return contour_from_mask(mask)


def circle_contour(r_px: float, canvas: int = 800) -> np.ndarray:
    mask = np.zeros((canvas, canvas), np.uint8)
    cv2.circle(mask, (canvas // 2, canvas // 2), int(r_px), 255, thickness=-1)
    return contour_from_mask(mask)


def ngon_contour(n: int, r_px: float, canvas: int = 800) -> np.ndarray:
    mask = np.zeros((canvas, canvas), np.uint8)
    pts = np.array(
        [[canvas // 2 + r_px * math.cos(2 * math.pi * k / n),
          canvas // 2 + r_px * math.sin(2 * math.pi * k / n)]
         for k in range(n)],
        np.int32,
    )
    cv2.fillPoly(mask, [pts], 255)
    return contour_from_mask(mask)


def star_contour(points: int = 5, r_out: float = 160, r_in: float = 45,
                 canvas: int = 800) -> np.ndarray:
    """Estrella con puntas muy agudas y salientes estrechas."""
    mask = np.zeros((canvas, canvas), np.uint8)
    pts = []
    for k in range(points * 2):
        a = 2 * math.pi * k / (points * 2) - math.pi / 2
        r = r_out if k % 2 == 0 else r_in
        pts.append([canvas // 2 + r * math.cos(a), canvas // 2 + r * math.sin(a)])
    cv2.fillPoly(mask, [np.array(pts, np.int32)], 255)
    return contour_from_mask(mask)


def notched_contour(canvas: int = 800) -> np.ndarray:
    """Rectángulo limpio con una muesca triangular profunda."""
    mask = np.zeros((canvas, canvas), np.uint8)
    pts = np.array(
        [[150, 150], [650, 150], [650, 650], [450, 650], [400, 380],
         [350, 650], [150, 650]],
        np.int32,
    )
    cv2.fillPoly(mask, [pts], 255)
    return contour_from_mask(mask)


def l_shape_contour(canvas: int = 800) -> np.ndarray:
    mask = np.zeros((canvas, canvas), np.uint8)
    cv2.rectangle(mask, (150, 150), (650, 300), 255, -1)
    cv2.rectangle(mask, (150, 300), (330, 650), 255, -1)
    return contour_from_mask(mask)


def jagged_contour(seed: int = 7, canvas: int = 800) -> np.ndarray:
    """Borde rasgado: polígono de 40 vértices perturbados aleatoriamente."""
    rng = np.random.default_rng(seed)
    mask = np.zeros((canvas, canvas), np.uint8)
    n = 40
    pts = []
    for k in range(n):
        a = 2 * math.pi * k / n
        r = 150 + float(rng.integers(-40, 41))
        pts.append([canvas // 2 + r * math.cos(a), canvas // 2 + r * math.sin(a)])
    cv2.fillPoly(mask, [np.array(pts, np.int32)], 255)
    return contour_from_mask(mask)


@pytest.fixture
def factor_k() -> float:
    return FACTOR_K


@pytest.fixture
def rect_200x120():
    """Rectángulo de 200×120 px → 2.00 × 1.20 m."""
    return rect_contour(200, 120)


@pytest.fixture
def db_manager(tmp_path):
    """DatabaseManager sobre una base temporal, con el schema migrado."""
    from data.database import DatabaseManager
    db = DatabaseManager(str(tmp_path / "test.db"))
    db.initialize()
    return db


@pytest.fixture
def repos(db_manager):
    """Los tres repositorios del almacén sobre la base temporal."""
    from data.storage_repositories import (
        ScrapRepository, ShelfRepository, StorageAreaRepository,
    )
    return (
        StorageAreaRepository(db_manager),
        ShelfRepository(db_manager),
        ScrapRepository(db_manager),
    )


@pytest.fixture
def warehouse(repos):
    """
    Almacén de prueba con reglas discriminantes.

        Estante 1 / Repisa 1  2.00 × 1.20 m  solo regulares, 0.5–2.0 × 0.5–2.5 m,
                                                 espesor ≥ 2 mm
        Estante 2 / Repisa 1  1.50 × 1.00 m  solo irregulares, 0.3–1.5 × 0.3–2.0 m
        Estante 2 / Repisa 2  0.50 × 0.50 m  ambas familias, sin límites
    """
    from core.entities import Shelf, ShelfRules, StorageArea
    area_repo, shelf_repo, _ = repos

    e1 = StorageArea(name="Estante 1")
    area_repo.save(e1)
    e2 = StorageArea(name="Estante 2")
    area_repo.save(e2)

    regular = shelf_repo.save(Shelf(
        storage_area_id=e1.id, name="Repisa 1", width_m=2.0, length_m=1.2,
        rules=ShelfRules(accepts_regular=True, accepts_irregular=False,
                         min_width_m=0.5, max_width_m=2.0,
                         min_length_m=0.5, max_length_m=2.5,
                         min_thickness_mm=2.0),
    ))
    irregular = shelf_repo.save(Shelf(
        storage_area_id=e2.id, name="Repisa 1", width_m=1.5, length_m=1.0,
        rules=ShelfRules(accepts_regular=False, accepts_irregular=True,
                         min_width_m=0.3, max_width_m=1.5,
                         min_length_m=0.3, max_length_m=2.0),
    ))
    small = shelf_repo.save(Shelf(
        storage_area_id=e2.id, name="Repisa 2", width_m=0.5, length_m=0.5,
    ))
    return {
        "repos": repos,
        "area_regular": e1.id, "area_irregular": e2.id,
        "regular": regular, "irregular": irregular, "small": small,
    }


def make_scrap(shape, length_m: float, width_m: float, **kwargs):
    """Construye un `Scrap` con valores por defecto razonables."""
    from core.entities import (
        Regularity, Scrap, ScrapDestination,
    )
    defaults = dict(
        area_m2=length_m * width_m,
        width_m=width_m,
        length_m=length_m,
        shape=shape,
        regularity=Regularity.REGULAR,
        destination=ScrapDestination.REUTILIZABLE,
    )
    defaults.update(kwargs)
    return Scrap(**defaults)
