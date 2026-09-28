"""
Detección de geometrías potencialmente punzantes (riesgo de corte).

ADVERTENCIA
-----------
Este módulo NO certifica seguridad industrial. Solo genera una **alerta de riesgo
potencial** a partir de la silueta observada por la cámara. Una alerta no significa
"esto es peligroso" y su ausencia no significa "esto es seguro". La decisión final
corresponde siempre a una persona.

Por qué no basta `if ángulo < 30°: peligro`
--------------------------------------------
Una lámina rectangular vista en perspectiva tiene las cuatro esquinas a 90° pero
puede reports 30-40° de error de medición sin que exista ninguna punta. Y un
triángulo perfectamente normal tiene un ángulo de 60° en su vértice, que un umbral
naive de 45° marcaría como peligro. Un umbral único produce demasiados falsos
positivos en ambas direcciones.

Por eso el score combina cinco señales independientes, y cada una tiene que
contribuir para que la alerta salte.
"""
from __future__ import annotations

import logging
import math
from typing import Optional

import cv2
import numpy as np

from core.entities import SharpnessReport

logger = logging.getLogger(__name__)

# ─── Pesos del score compuesto (suman 1.0) ───────────────────────────────────
W_MIN_ANGLE: float = 0.30
W_PROTRUSION: float = 0.25
W_SPIKE: float = 0.20
W_CONVEXITY_DEFECT: float = 0.15
W_LOCAL_ASPECT: float = 0.10

# ─── Umbrales de las señales ──────────────────────────────────────────────────
# El ángulo interior por debajo del cual un vértice empieza a ser sospechoso.
ACUTE_ANGLE_DEG: float = 50.0
# Ángulo en el que la señal de ángulo alcanza su máximo.
MIN_ANGLE_FLOOR_DEG: float = 0.0
# Protrusión (1 − hull/area) a partir de la cual la señal satura.
PROTRUSION_SATURATION: float = 0.25
# Un "spike" tiene un factor de arista ≥ este valor respecto a la mediana.
SPIKE_THRESHOLD: float = 1.8
# Defecto de convexidad (0..1) a partir del cual la señal satura.
DEFECT_SATURATION: float = 0.6
# Relación de aspecto local (p90/min) a partir de la cual la señal satura.
LOCAL_ASPECT_SATURATION: float = 6.0

# ─── Separación mínima entre vértices en px (ruido de la polilínea) ───────────
MIN_VERTEX_SPACING_PX: float = 3.0


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else (1.0 if value > 1.0 else value)


def _resample(contour: np.ndarray, simplify_ratio: float = 0.01) -> np.ndarray:
    """
    Simplifica el contorno para medir ángulos sobre una polilínea estable.

    Con el ratio 0.01 (1 % del perímetro) se conservan las esquinas reales y se
    elimina el dentado del ruido de segmentación, que generaría ángulos
    agudos falsos en cada borde.
    """
    peri = cv2.arcLength(contour, True)
    if peri <= 0:
        return contour.reshape(-1, 2)
    eps = max(1.0, peri * simplify_ratio)
    approx = cv2.approxPolyDP(contour, eps, True)
    if len(approx) < 3:
        approx = cv2.approxPolyDP(contour, max(1.0, peri * simplify_ratio * 3), True)
    return approx.reshape(-1, 2) if len(approx) >= 3 else contour.reshape(-1, 2)


def _min_internal_angle(poly: np.ndarray) -> float:
    """
    Ángulo interno más pequeño (en grados) de la polilínea cerrada.

    Devuelve 180.0 si la polilínea tiene menos de 3 vértices utilizables
    (no se puede formar un ángulo) — se trata como "no suspeito".
    """
    n = len(poly)
    if n < 3:
        return 180.0

    pts = poly.astype(np.float64)
    min_angle = 180.0

    for i in range(n):
        prev_p = pts[(i - 1) % n]
        cur_p = pts[i]
        next_p = pts[(i + 1) % n]

        v1 = prev_p - cur_p
        v2 = next_p - cur_p
        n1 = math.hypot(v1[0], v1[1])
        n2 = math.hypot(v2[0], v2[1])
        if n1 < MIN_VERTEX_SPACING_PX or n2 < MIN_VERTEX_SPACING_PX:
            continue

        cos_a = float(np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0))
        angle = math.degrees(math.acos(cos_a))
        if angle < min_angle:
            min_angle = angle

    return min_angle


def _edge_length_stats(poly: np.ndarray) -> tuple[float, np.ndarray]:
    """Devuelve (longitud mediana de arista, array de longitudes)."""
    pts = poly.astype(np.float64)
    deltas = np.roll(pts, -1, axis=0) - pts
    lengths = np.hypot(deltas[:, 0], deltas[:, 1])
    if lengths.size == 0:
        return 0.0, lengths
    return float(np.median(lengths)), lengths


def _spike_factor(poly: np.ndarray, median_edge: float) -> float:
    """
    Factor de espina: cuánto sobresalen los vértices más "hocudos" frente a
    la arista típica de la propia pieza.

    Un rectángulo tiene spike_factor bajo (0) porque todas sus vértices son
    "normales" respecto a sus propias aristas. Una lengüeta o una astilla
    estrecha tiene vértices cuyas aristas vecinas son mucho más cortas que la
    mediana, lo que produce un factor alto.
    """
    if median_edge <= 0 or len(poly) < 3:
        return 0.0

    n = len(poly)
    pts = poly.astype(np.float64)
    factors: list[float] = []

    for i in range(n):
        prev_p = pts[(i - 1) % n]
        cur_p = pts[i]
        next_p = pts[(i + 1) % n]
        d_prev = math.hypot(cur_p[0] - prev_p[0], cur_p[1] - prev_p[1])
        d_next = math.hypot(next_p[0] - cur_p[0], next_p[1] - cur_p[1])
        local = min(d_prev, d_next)
        if local < MIN_VERTEX_SPACING_PX:
            continue
        factors.append(local / median_edge)

    if not factors:
        return 0.0
    return _clamp01(max(factors) / SPIKE_THRESHOLD)


def _local_aspect(poly: np.ndarray) -> float:
    """
    Relación entre el percentil 90 y el mínimo de los anchos locales.

    Detecta "lengüetas" y astillas: una pieza normal tiene lados de ancho
    comparable; una pieza con una punta estrecha tiene un lado mucho más fino
    que el resto.
    """
    if len(poly) < 3:
        return 1.0

    pts = poly.astype(np.float64)
    n = len(pts)
    widths: list[float] = []

    for i in range(n):
        prev_p = pts[(i - 1) % n]
        cur_p = pts[i]
        next_p = pts[(i + 1) % n]

        arista = next_p - prev_p
        largo = math.hypot(arista[0], arista[1])
        if largo < MIN_VERTEX_SPACING_PX:
            continue
        # Distancia de `cur_p` a la recta que une prev_p y next_p = ancho local
        ancho = abs(
            arista[0] * (prev_p[1] - cur_p[1]) - (prev_p[0] - cur_p[0]) * arista[1]
        ) / largo
        if ancho > 0:
            widths.append(ancho)

    if len(widths) < 2:
        return 1.0

    p90 = float(np.percentile(widths, 90))
    min_w = float(np.min(widths))
    if min_w <= 0:
        return LOCAL_ASPECT_SATURATION
    return max(1.0, p90 / min_w)


def _convexity_defect_signal(contour: np.ndarray) -> float:
    """Señal de defectos de convexidad normalizada a [0, 1]."""
    try:
        hull = cv2.convexHull(contour, returnPoints=False)
        defects = cv2.convexityDefects(contour, hull)
    except cv2.error:
        return 0.0
    if defects is None or len(defects) == 0:
        return 0.0

    # cv2.convexityDefects[] [0, 1, 2] = profundidad / 256. Solo importan los
    # defectos con profundidad apreciable: el ruido genera defectos de 0.
    depths = [float(d[0][3]) / 256.0 for d in defects if d[0][3] > 0]
    if not depths:
        return 0.0
    max_depth = max(depths)
    return _clamp01(max_depth / max(DEFECT_SATURATION, 1e-6))


def analyze_sharpness(contour: np.ndarray, threshold: float = 0.55) -> Optional[SharpnessReport]:
    """
    Calcula el `sharpness_score` compuesto de un contorno.

    Args:
        contour:   Contorno Nx1x2 de OpenCV.
        threshold: Score a partir del cual se dispara la alerta (configurable).

    Returns:
        SharpnessReport, o None si el contorno es degenerado.
    """
    if contour is None:
        return None

    area = cv2.contourArea(contour)
    if area <= 0:
        return None

    hull_area = cv2.contourArea(cv2.convexHull(contour))
    protrusion = _clamp01(1.0 - area / hull_area) if hull_area > 0 else 0.0

    poly = _resample(contour)
    min_angle = _min_internal_angle(poly)
    median_edge, _ = _edge_length_stats(poly)
    spike = _spike_factor(poly, median_edge)
    defect_signal = _convexity_defect_signal(contour)
    local_aspect = _local_aspect(poly)

    # ── Normalización de cada señal a [0, 1] ────────────────────────────────
    # Ángulo: 0° → 1.0 (máximo riesgo), ACUTE_ANGLE_DEG o más → 0.0
    if min_angle >= ACUTE_ANGLE_DEG:
        s_angle = 0.0
    else:
        s_angle = _clamp01(
            (ACUTE_ANGLE_DEG - min_angle) / max(ACUTE_ANGLE_DEG - MIN_ANGLE_FLOOR_DEG, 1e-6)
        )

    s_protrusion = _clamp01(protrusion / PROTRUSION_SATURATION)
    s_local = _clamp01((local_aspect - 1.0) / max(LOCAL_ASPECT_SATURATION - 1.0, 1e-6))

    score = (
        W_MIN_ANGLE * s_angle
        + W_PROTRUSION * s_protrusion
        + W_SPIKE * spike
        + W_CONVEXITY_DEFECT * defect_signal
        + W_LOCAL_ASPECT * s_local
    )
    score = _clamp01(score)

    report = SharpnessReport(
        score=score,
        min_internal_angle_deg=min_angle,
        protrusion_depth=protrusion,
        spike_factor=round(spike * SPIKE_THRESHOLD, 3),
        convexity_defect_ratio=defect_signal,
        local_aspect=local_aspect,
        triggered=score >= threshold,
    )

    logger.debug(
        "Sharpness | score=%.3f angle=%.1f° protr=%.3f spike=%.2f defect=%.2f local=%.2f → %s",
        report.score, report.min_internal_angle_deg, report.protrusion_depth,
        report.spike_factor, report.convexity_defect_ratio, report.local_aspect,
        "ALERTA" if report.triggered else "ok",
    )
    return report
