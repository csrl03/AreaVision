"""
Clasificación geométrica de retales a partir del contorno de OpenCV.

Sin dependencias de UI, de red o de base de datos. Solo numpy + OpenCV.

Estrategia
----------
Ninguna métrica decide por sí sola. Se combinan cinco evidencias:

1. `approxPolyDP` con ε proporcional al perímetro → nº de vértices
2. `cv2.minAreaRect` → **dimensiones físicas reales** (agnóstico a la inclinación)
3. `solidez = área / área_del_hull_convexo` → separa polígonos simples de cóncavos
4. `circularidad = 4πA / P²` → distingue disco de polígono
5. `convexityDefects` → número de indentaciones del hull convexo

Sobre el minAreaRect
--------------------
`ProcessingResult.aspect_ratio` usa `cv2.boundingRect`, que devuelve el rectángulo
**alineado a los ejes**. Una pieza de 1.20 × 0.40 m girada 45° reporta aspecto ≈1.0
en lugar de ≈3.0, y toda la clasificación se desvía. Este módulo usa
`minAreaRect` (rectángulo mínimo rotado) y devuelve el ángulo, de modo que las
dimensiones son correctas sin importar la orientación de la pieza frente a la cámara.
"""
from __future__ import annotations

import logging
import math
from typing import Optional

import cv2
import numpy as np

from core.entities import GeometryAnalysis, Regularity, ShapeType

logger = logging.getLogger(__name__)

# ─── Umbrales geométricos (valores por defecto; ajustables por el servicio) ───
DEFAULT_SIMPLIFY_RATIO: float = 0.02   # ε de approxPolyDP como fracción del perímetro

CIRCULARITY_CIRCLE: float = 0.84        # circularidad mínima para considerar círculo
CIRCLE_HULL_ERROR: float = 0.06        # |area − hull_area| / hull_area para círculo limpio
CIRCLE_MIN_AREA_DEFICIT: float = 0.05  # ver _area_deficit(): separa disco de polígono
SQUARE_ASPECT_TOL: float = 0.12        # |aspecto − 1| para considerar cuadrado
SOLIDITY_SQUARE: float = 0.95
SOLIDITY_RECTANGLE: float = 0.90
SOLIDITY_TRIANGLE: float = 0.80
SOLIDITY_REGULAR_POLYGON: float = 0.85
MIN_VERTICES_REGULAR_POLYGON: int = 5
MAX_VERTICES_REGULAR_POLYGON: int = 8
SIDE_VARIANCE_REGULAR: float = 0.25    # coeficiente de variación máximo de los lados
ANGLE_VARIANCE_REGULAR: float = 0.20   # coeficiente de variación máximo de los ángulos
SMOOTH_VERTEX_FLOOR: float = 6.0       # hasta este nº de vértices, contorno limpio
SMOOTH_VERTEX_CEIL: float = 20.0       # a partir de aquí, contorno áspero
DEFECT_SATURATION_REL: float = 0.15    # profundidad de muesca / lado corto que satura el score

REGULAR_SOLIDITY_AT: float = 0.92
IRREGULAR_SOLIDITY_BELOW: float = 0.75
IRREGULAR_DEFECTS: int = 3


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)


def _contour_to_polygon(contour: np.ndarray, simplify_ratio: float) -> np.ndarray:
    """
    Simplifica el contorno a una polilínea de pocos vértices.

    Es la etapa que evita convertir una máscara ruidosa de miles de puntos en
    miles de entidades CAD. El mismo polígono sirve para clasificar, medir
    ángulos y exportar DXF.
    """
    peri = cv2.arcLength(contour, True)
    if peri <= 0:
        return contour.reshape(-1, 2)
    epsilon = max(1.0, peri * simplify_ratio)
    approx = cv2.approxPolyDP(contour, epsilon, True)
    if len(approx) < 3:
        # Un contorno tan ruidoso que la simplificación lo destruye:
        # se recorta el número de vértices con una tolerancia mayor.
        approx = cv2.approxPolyDP(contour, peri * simplify_ratio * 3, True)
    if len(approx) < 3:
        return contour.reshape(-1, 2)
    return approx.reshape(-1, 2)


def _side_lengths(poly: np.ndarray) -> list[float]:
    """Longitud de cada arista del polígono cerrado."""
    pts = poly.astype(np.float64)
    deltas = np.roll(pts, -1, axis=0) - pts
    return [float(math.hypot(d[0], d[1])) for d in deltas]


def _circularity_hull_error(contour: np.ndarray) -> tuple[float, float]:
    """Devuelve (circularidad, error relativo área vs. hull)."""
    area = cv2.contourArea(contour)
    peri = cv2.arcLength(contour, True)
    if peri <= 0 or area <= 0:
        return 0.0, 1.0
    circ = (4.0 * math.pi * area) / (peri ** 2)
    hull_area = cv2.contourArea(cv2.convexHull(contour))
    err = abs(area - hull_area) / hull_area if hull_area > 0 else 1.0
    return _clamp01(circ), _clamp01(err)


def _count_convexity_defects(contour: np.ndarray) -> int:
    """Número de defectos de convexidad (indentaciones del hull)."""
    try:
        hull = cv2.convexHull(contour, returnPoints=False)
        defects = cv2.convexityDefects(contour, hull)
        return 0 if defects is None else int(len(defects))
    except cv2.error:
        return 0


def _coefficient_of_variation(values: list[float]) -> float:
    """Desviación típica relativa. 0 = todos los valores iguales."""
    if len(values) < 2:
        return 1.0
    mean = sum(values) / len(values)
    if mean <= 0:
        return 1.0
    return float(np.std(values) / mean)


def _internal_angles(poly: np.ndarray) -> list[float]:
    """Ángulos internos de la polilínea cerrada, en grados (0..180)."""
    n = len(poly)
    if n < 3:
        return []
    pts = poly.astype(np.float64)
    angles: list[float] = []
    for i in range(n):
        v1 = pts[(i - 1) % n] - pts[i]
        v2 = pts[(i + 1) % n] - pts[i]
        n1 = math.hypot(v1[0], v1[1])
        n2 = math.hypot(v2[0], v2[1])
        if n1 < 1e-6 or n2 < 1e-6:
            continue
        cos_a = float(np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0))
        angles.append(math.degrees(math.acos(cos_a)))
    return angles


def _defect_depth_ratio(contour: np.ndarray) -> float:
    """
    Profundidad de la muesca más profunda, relativa al lado corto de la pieza.

    Importa usar la *profundidad* y no el *recuento* de defectos de convexidad.
    Un círculo digitalizado de 200 px produce 2-3 defectos de 1 px por la
    escalera de píxeles; contarlos lo penalizaría como si tuviera un corte
    profundo. Midiendo la profundidad contra el tamaño real de la pieza, esa
    muesca de 1 px vale 1/200 = 0.005 y se ignora, mientras que una V de 60 px
    en la misma pieza vale 0.30 y satura la señal.

    Returns:
        Razón profundidad / lado_corto. 0.0 si no hay defectos o no se puede medir.
    """
    try:
        hull = cv2.convexHull(contour, returnPoints=False)
        defects = cv2.convexityDefects(contour, hull)
    except cv2.error:
        return 0.0
    if defects is None or len(defects) == 0:
        return 0.0

    depths = [float(d[0][3]) / 256.0 for d in defects if d[0][3] > 0]
    if not depths:
        return 0.0

    (_, (rw, rh), _) = cv2.minAreaRect(contour)
    short_side = min(rw, rh)
    if short_side <= 0:
        return 0.0
    return max(depths) / short_side


def _regularity_score(
    solidity: float,
    defect_depth_ratio: float,
    vertex_count: int,
) -> float:
    """
    Score continuo de regularidad en [0, 1], en [0, 1].

    Responde a: *"¿este contorno parece un corte limpio de máquina o un borde
    rasgado?"*. NO responde a *"¿es simétrico?"*.

    Es una distinción importante. Un rectángulo tiene lados [L, W, L, W]: su
    coeficiente de variación de lados es |L−W|/(L+W), o sea 0.25 para un 2:1 y
    0.50 para un 3:1. Cualquier medida de simetría marcaría como irregular un
    rectángulo perfectamente limpio, y en un almacén de recortes eso es un falso
    negativo constante. La regularidad de un retal se decide por la suavidad del
    contorno, no por su simetría.

        weights = solidez 0.40 · suavidad 0.35 · muesca 0.25

    `vertex_count` actúa de proxy de suavidad: `approxPolyDP` colapsa un corte
    limpio en 3-8 vértices, pero necesita 30+ para seguir el dentado de una
    rotura de chapa. La rampa tiene suelo (`SMOOTH_VERTEX_FLOOR`) para que un
    cuadrado de 4 vértices puntúe 1.0 en vez de perder puntos por ser "poco
    redondeado", y techo (`SMOOTH_VERTEX_CEIL`) para que la sierra caiga a 0.

        cuadrado  → 1.000        L-shape   → 0.85  (dos cortes rectos, limpio)
        hexágono  → 1.000        muesca    → 0.88
        octágono  → 0.950        estrella  → 0.60  (irregular)
        círculo   → 0.950        sierra    → 0.51  (irregular)
    """
    w_solidity = 0.40
    w_smoothness = 0.35
    w_notch = 0.25

    solidity_term = _clamp01(solidity)
    span = max(SMOOTH_VERTEX_CEIL - SMOOTH_VERTEX_FLOOR, 1e-6)
    smoothness_term = _clamp01(
        1.0 - (vertex_count - SMOOTH_VERTEX_FLOOR) / span
    )
    notch_term = _clamp01(1.0 - defect_depth_ratio / DEFECT_SATURATION_REL)

    return _clamp01(
        w_solidity * solidity_term
        + w_smoothness * smoothness_term
        + w_notch * notch_term
    )


def _area_deficit(contour: np.ndarray, poly: np.ndarray) -> float:
    """
    Cuánta área "pierde" la polilínea simplificada respecto al contorno real.

    Este es el discriminante clave entre un disco y un polígono regular:

        círculo r=100 px      → deficit ≈ 0.094
        hexágono  r=100 px    → deficit ≈ 0.003
        cuadrado 200 px       → deficit ≈ 0.000

    Tiene sentido geométrico: un polígono regular se puede representar con
    exactamente sus n vértices, así que `approxPolyDP` lo reproduce sin perder
    nada. Un círculo, en cambio, no tiene un número finito de vértices: cualquier
    polilínea inscrita queda dentro, y con 8 lados el polígono regular es
    cos(π/8) ≈ 0.924 del círculo, es decir un déficit del 7.6 %.

    Los dos casos se separan por un orden de magnitud, así que el umbral es
    amplio y no sensible al ruido de segmentación.
    """
    area = cv2.contourArea(contour)
    if area <= 0:
        return 0.0
    return _clamp01((area - cv2.contourArea(poly)) / area)


def _classify(
    poly: np.ndarray,
    circularity: float,
    solidity: float,
    hull_error: float,
    area_deficit: float,
    aspect_ratio: float,
) -> tuple[ShapeType, float]:
    """
    Aplica las reglas de decisión → (forma, confianza_heurística).

    La confianza mide el margen con el que la regla se cumple, no una certeza
    física. Un 0.9 significa "las evidencias apuntan claramente aquí", no
    "garantizado al 90 %".
    """
    n = len(poly)
    sides = _side_lengths(poly)
    side_mean = sum(sides) / len(sides) if sides else 0.0
    side_cv = (
        float(np.std(sides) / side_mean) if side_mean > 0 and len(sides) > 2 else 1.0
    )

    # ── Círculo: tres evidencias concordantes ───────────────────────────────
    # 1. circularidad alta   (descarta cuadrado 0.785, triángulo 0.54)
    # 2. hull casi idéntico al contorno (descarta formas cóncavas)
    # 3. déficit de área alto (descarta hexágono 0.82, octágono 0.81)
    # Exigir las tres evita que un polígono regular de 6-8 lados se lea como disco.
    if (
        circularity >= CIRCULARITY_CIRCLE
        and hull_error <= CIRCLE_HULL_ERROR
        and area_deficit >= CIRCLE_MIN_AREA_DEFICIT
    ):
        circ_margin = _clamp01((circularity - CIRCULARITY_CIRCLE) / (1.0 - CIRCULARITY_CIRCLE))
        hull_margin = _clamp01(1.0 - hull_error / max(CIRCLE_HULL_ERROR, 1e-6))
        return ShapeType.CIRCULO, _clamp01(0.55 + 0.20 * circ_margin + 0.10 * hull_margin + 0.15)

    # ── Cuadrado: 4 vértices, muy sólido y lados iguales ──
    if n == 4 and solidity >= SOLIDITY_SQUARE and abs(aspect_ratio - 1.0) <= SQUARE_ASPECT_TOL:
        margin = _clamp01((solidity - SOLIDITY_SQUARE) / max(1.0 - SOLIDITY_SQUARE, 1e-6))
        aspect_ok = _clamp01(1.0 - abs(aspect_ratio - 1.0) / max(SQUARE_ASPECT_TOL, 1e-6))
        return ShapeType.CUADRADO, _clamp01(0.60 + 0.20 * margin + 0.20 * aspect_ok)

    # ── Triángulo ──
    if n == 3 and solidity >= SOLIDITY_TRIANGLE:
        margin = _clamp01((solidity - SOLIDITY_TRIANGLE) / max(1.0 - SOLIDITY_TRIANGLE, 1e-6))
        return ShapeType.TRIANGULO, _clamp01(0.60 + 0.30 * margin)

    # ── Rectángulo: 4 vértices, sólido, pero no cuadrado ──
    if n == 4 and solidity >= SOLIDITY_RECTANGLE:
        margin = _clamp01((solidity - SOLIDITY_RECTANGLE) / max(1.0 - SOLIDITY_RECTANGLE, 1e-6))
        return ShapeType.RECTANGULO, _clamp01(0.55 + 0.30 * margin + 0.15 * (1.0 - side_cv))

    # ── Polígono regular ──
    if (
        MIN_VERTICES_REGULAR_POLYGON <= n <= MAX_VERTICES_REGULAR_POLYGON
        and solidity >= SOLIDITY_REGULAR_POLYGON
        and side_cv <= SIDE_VARIANCE_REGULAR
    ):
        margin = _clamp01((solidity - SOLIDITY_REGULAR_POLYGON) / max(1.0 - SOLIDITY_REGULAR_POLYGON, 1e-6))
        uniformity = _clamp01(1.0 - side_cv / max(SIDE_VARIANCE_REGULAR, 1e-6))
        return ShapeType.POLIGONO_REGULAR, _clamp01(0.50 + 0.25 * margin + 0.25 * uniformity)

    # ── Polígono irregular vs. desconocida ──
    if n >= 3:
        return ShapeType.POLIGONO_IRREGULAR, 0.45
    return ShapeType.OTRA, 0.20


def analyze_contour(
    contour: np.ndarray,
    factor_k: float,
    simplify_ratio: float = DEFAULT_SIMPLIFY_RATIO,
    regular_at: float = REGULAR_SOLIDITY_AT,
    irregular_below: float = IRREGULAR_SOLIDITY_BELOW,
) -> Optional[GeometryAnalysis]:
    """
    Analiza un contorno de OpenCV y devuelve su geometría en unidades reales.

    Args:
        contour:       Contorno Nx1x2 devuelto por `cv2.findContours`.
        factor_k:      FactorK vigente (m²/px²). Convierte longitudes px → metros.
        simplify_ratio: ε de `approxPolyDP` como fracción del perímetro.
        regular_at:    Score de regularidad a partir del cual se considera REGULAR.
        irregular_below: Score a partir del cual se considera IRREGULAR.

    Returns:
        GeometryAnalysis, o None si el contorno es degenerado (área 0, perímetro 0
        o factor_k inválido).
    """
    if contour is None or factor_k <= 0:
        return None

    area_px = cv2.contourArea(contour)
    perimeter_px = cv2.arcLength(contour, True)
    if area_px <= 0 or perimeter_px <= 0:
        logger.debug("Contorno degenerado descartado (área=%.1f perim=%.1f)", area_px, perimeter_px)
        return None

    poly = _contour_to_polygon(contour, simplify_ratio)
    circularity, hull_error = _circularity_hull_error(contour)

    hull_area = cv2.contourArea(cv2.convexHull(contour))
    solidity = _clamp01(area_px / hull_area) if hull_area > 0 else 0.0

    defects = _count_convexity_defects(contour)

    # ── Dimensiones reales: rectángulo mínimo ROTADO ──
    (_, (rw, rh), _) = cv2.minAreaRect(contour)
    if min(rw, rh) < 1e-6:
        long_px, short_px = float(perimeter_px / 4.0), float(perimeter_px / 4.0)
    else:
        long_px, short_px = max(rw, rh), min(rw, rh)

    # factor_k es m²/px² → su raíz cuadrada convierte longitudes px → metros.
    m_per_px = math.sqrt(factor_k)
    length_m = long_px * m_per_px
    width_m = short_px * m_per_px

    aspect_ratio = (long_px / short_px) if short_px > 0 else 1.0

    area_deficit = _area_deficit(contour, poly)
    shape, confidence = _classify(
        poly, circularity, solidity, hull_error, area_deficit, aspect_ratio
    )
    reg_score = _regularity_score(
        solidity=solidity,
        defect_depth_ratio=_defect_depth_ratio(contour),
        vertex_count=len(poly),
    )
    regularity = Regularity.from_score(reg_score, regular_at=regular_at, irregular_below=irregular_below)

    # El área reportada es la del FactorK (medición calibrada), no la del
    # rectángulo mínimo: un rectángulo con un triángulo dentro tiene bounding
    # mayor que su área real.
    return GeometryAnalysis(
        shape=shape,
        regularity=regularity,
        regularity_score=reg_score,
        confidence=confidence,
        width_m=width_m,
        length_m=length_m,
        vertex_count=len(poly),
        circularity=circularity,
        solidity=solidity,
        convexity_defects=defects,
        area_m2=area_px * factor_k,
    )
