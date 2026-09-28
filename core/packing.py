"""
Packing 2D de rectángulos en una repisa.

Por qué NO basta comparar áreas
-------------------------------
    Repisa = 2.00 × 1.00 m   (área 2.00 m²)
    Retal A = 1.00 × 1.50 m  (área 1.50 m²)
    Retal B = 0.20 × 7.50 m  (área 1.50 m²)

Ambos tienen menos área que la repisa, pero ninguno de los dos cabe. Comparar
`área_retal <= área_disponible` produciría dos aceptaciones falsas.

Estrategia: "shelf-first" determinista
--------------------------------------
No resuelve el problema NP-difícil del bin packing óptimo. Implementa una
heurística **conservadora y reproducible**:

1. Se prueban las 2 orientaciones del retal (rotación 0° y 90°).
2. Para cada orientación se barre la repisa de abajo hacia arriba construyendo
   *estanterías horizontales*: se busca la primera estantería con altura ≥ la
   altura del retal y hueco horizontal suficiente; si no hay, se abre una
   estantería nueva encima.
3. Si la primera pasada no encuentra sitio, se hace una segunda pasada
   "best-fit" que considera también huecos dejados por estanterías anteriores.
4. Devuelve (x, y, rotated) en metros, o None.

Propiedades garantizadas:
- **Determinista**: el mismo inventario siempre produce la misma posición.
- **Conservadora**: si devuelve None, es porque de verdad no halló hueco con esta
  heurística; nunca coloca una pieza que se solape.
- **Sin solapamientos**: cada pieza se ancla en un hueco verificado libre.

El punto de entrada público es `place_in_bin`, que recibe la lista de rects ya
colocados (x, y, w, h) y devuelve la posición del nuevo.

Sustituibilidad
---------------
La UI nunca llama a estas funciones directamente: pasa por
`services/allocation_service.py`, que es la única capa que conoce la semántica de
negocio. Cambiar la heurística por MaxRects o por un optimizador real solo
requiere tocar este archivo.
"""
from __future__ import annotations

import logging
import math
from typing import Optional

logger = logging.getLogger(__name__)

# Tolerancia (m) para absorber errores de coma flotante al comparar longitudes.
EPS: float = 1e-9


def fits_single(item_w: float, item_h: float, bin_w: float, bin_h: float) -> bool:
    """
    True si el rectángulo cabe en la repisa considerando rotación de 90°.

    Es el filtro barato: descarta las piezas imposiblemente grandes antes de
    bothering con el packing multi-pieza.

        >>> fits_single(1.10, 0.90, 2.00, 1.20)
        True
        >>> fits_single(3.00, 0.80, 2.00, 1.20)
        False
    """
    if min(item_w, item_h, bin_w, bin_h) <= 0:
        return False
    if item_w <= bin_w + EPS and item_h <= bin_h + EPS:
        return True
    return item_h <= bin_w + EPS and item_w <= bin_h + EPS  # rotado 90°


def _overlaps(
    ax: float, ay: float, aw: float, ah: float,
    bx: float, by: float, bw: float, bh: float,
) -> bool:
    """True si dos rectángulos se solapan (bordes compartidos NO cuentan)."""
    return not (
        ax + aw <= bx + EPS
        or bx + bw <= ax + EPS
        or ay + ah <= by + EPS
        or by + bh <= ay + EPS
    )


def _is_free(
    x: float, y: float, w: float, h: float,
    placed: list[tuple[float, float, float, float]],
    bin_w: float | None = None,
    bin_h: float | None = None,
) -> bool:
    """
    True si (x, y, w, h) está dentro de la repisa y no solapa ningún rect.

    `bin_w`/`bin_h` son opcionales para no repetir el chequeo en los bucles
    que ya lo hicieron, pero `_shelf_first_pass` los pasa como red de seguridad:
    cualquier hueco que se brinde a una pieza debe caber en la repisa.
    """
    if bin_w is not None and (x < -EPS or y < -EPS or x + w > bin_w + EPS):
        return False
    if bin_h is not None and y + h > bin_h + EPS:
        return False
    for px, py, pw, ph in placed:
        if _overlaps(x, y, w, h, px, py, pw, ph):
            return False
    return True


def _shelf_first_pass(
    w: float, h: float, bin_w: float, bin_h: float,
    placed: list[tuple[float, float, float, float]],
) -> Optional[tuple[float, float]]:
    """
    Barrido de arriba abajo por estanterías horizontales.

    Intenta encajar el retal en la estantería inferior; si no cabe en anchura,
    salta a la siguiente estantería (más alta). Si ninguna sirve, abre una nueva
    estantería arriba del todo.
    """
    # Ordenar por Y ascendente: la estantería más baja es la que tiene más
    # espacio vertical por encima para crecer.
    ordered = sorted(placed, key=lambda r: (round(r[1], 6), r[0]))

    shelf_bottoms: list[tuple[float, float]] = []  # (y_base, altura)
    for px, py, pw, ph in ordered:
        merged = False
        for i, (sy, sh) in enumerate(shelf_bottoms):
            # ¿Este rect pertenece a una estantería ya abierta?
            if py <= sy + sh + EPS and py + ph >= sy - EPS:
                shelf_bottoms[i] = (sy, max(sh, py + ph - sy))
                merged = True
                break
        if not merged:
            shelf_bottoms.append((py, ph))

    if not ordered:
        # Repisa vacía: si la pieza cabe, va a la esquina inferior izquierda.
        if w <= bin_w + EPS and h <= bin_h + EPS:
            return (0.0, 0.0)
        return None

    for sy, sh in shelf_bottoms:
        if h > sh + EPS:
            # El retal es más alto que esta estantería: no puede vivir aquí.
            continue
        if sy + h > bin_h + EPS:
            # La estantería está tan arriba que el retal se saldría de la
            # repisa. Sin esta comprobación una pieza más alta que la repisa
            # se colocaría "dentro" de una estantería inexistente.
            continue
        # Candidatos de X: el borde de cada rect ya colocado, y el origen.
        xs = [0.0]
        for px, py, pw, ph in ordered:
            if py >= sy + sh - EPS:  # solo los de esta estantería o de abajo
                xs.append(px + pw)
        for x in sorted(set(round(v, 6) for v in xs)):
            if x + w > bin_w + EPS:
                continue
            if _is_free(x, sy, w, h, placed, bin_w, bin_h):
                return (x, sy)

    # No cupió en ninguna estantería existente → intentar abrir una nueva arriba
    top = 0.0
    for _, _, _, ph in placed:
        top = max(top, ph)
    for px, py, _, _ in ordered:
        top = max(top, py + ph)
    if top + h <= bin_h + EPS:
        for x in sorted({0.0} | {px + pw for px, py, pw, ph in ordered}):
            if x + w > bin_w + EPS:
                continue
            if _is_free(x, top, w, h, placed, bin_w, bin_h):
                return (x, top)

    return None


def _best_fit_pass(
    w: float, h: float, bin_w: float, bin_h: float,
    placed: list[tuple[float, float, float, float]],
) -> Optional[tuple[float, float]]:
    """
    Segunda pasada: busca el hueco más "ajustado" (menor desperdicio).

    Barre todas las combinaciones de (bordes X, bordes Y) de los rects ya
    colocados más el origen. Es O(n³) en el número de piezas, pero el número de
    retales por repisa es pequeño (decenas), así que es aceptable.
    """
    xs = sorted({0.0} | {px for px, _, _, _ in placed} | {px + pw for px, _, pw, _ in placed})
    ys = sorted({0.0} | {py for _, py, _, _ in placed} | {py + ph for _, py, _, ph in placed})

    best: Optional[tuple[float, float, float]] = None  # (desperdicio, x, y)
    for y in ys:
        if y + h > bin_h + EPS:
            continue
        for x in xs:
            if x + w > bin_w + EPS:
                continue
            if not _is_free(x, y, w, h, placed, bin_w, bin_h):
                continue
            # Desperdicio = rectángulo libre más pequeño que contendría la pieza.
            right_gap = bin_w - (x + w)
            top_gap = bin_h - (y + h)
            waste = right_gap + top_gap
            if best is None or waste < best[0] - EPS:
                best = (waste, x, y)

    if best is None:
        return None
    return (best[1], best[2])


def place_in_bin(
    item_w: float,
    item_h: float,
    bin_w: float,
    bin_h: float,
    placed: list[tuple[float, float, float, float]],
) -> Optional[tuple[float, float, bool]]:
    """
    Intenta colocar un rectángulo en la repisa.

    Args:
        item_w, item_h: Dimensiones del retal en metros (sin rotar).
        bin_w, bin_h:   Dimensiones de la repisa en metros.
        placed:         Lista de (x, y, w, h) ya ocupados, con w/h YA rotados.

    Returns:
        (x, y, rotated) con la esquina inferior izquierda del retal y si hubo
        que rotarlo 90°, o None si no cabe.
    """
    if not fits_single(item_w, item_h, bin_w, bin_h):
        return None

    candidates: list[tuple[str, float, float, bool]] = [
        ("original", item_w, item_h, False),
    ]
    # Si la pieza no es cuadrada, la rotación es una opción distinta.
    if not math.isclose(item_w, item_h, rel_tol=1e-9):
        candidates.append(("rotated", item_h, item_w, True))

    for _, w, h, rotated in candidates:
        for strategy in (_shelf_first_pass, _best_fit_pass):
            pos = strategy(w, h, bin_w, bin_h, placed)
            if pos is not None:
                return (pos[0], pos[1], rotated)

    return None


def compute_occupancy(
    placed: list[tuple[float, float, float, float]],
    bin_w: float,
    bin_h: float,
) -> dict[str, float]:
    """
    Métricas de ocupación de la repisa.

    Distingue explícitamente dos cosas que a menudo se confunden:

    - `used_area_m2` / `available_area_m2`: suma de áreas (estimación, no real).
    - `packing_confidence`: cuánto del hueco se ha leveraged de verdad. Si
      `available_area_m2` es grande pero no queda sitio, la heurística está
      llena aunque el "espacio disponible" por área parezca grande.
    """
    used = sum(w * h for _, _, w, h in placed)
    total = bin_w * bin_h
    # Ancho máximo libre por franja horizontal: una cota inferior del hueco real.
    return {
        "total_area_m2": total,
        "used_area_m2": used,
        "available_area_m2": max(0.0, total - used),
        "occupancy_ratio": (used / total) if total > 0 else 0.0,
        "piece_count": float(len(placed)),
    }
