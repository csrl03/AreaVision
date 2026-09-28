"""
Servicio de asignación automática de retales a repisas.

    geometría + seguridad + espesor
        ↓  (ClassificationService ya decidió REUTILIZABLE)
    find_compatible_locations(...)
        ↓  filtra por reglas de cada repisa
    check_physical_space(...)
        ↓  packing 2D real con rotación de 90° (core.packing)
    allocate_best_location(...)
        ↓
    AllocationProposal

Diferencia clave con el enfoque ingenuo
---------------------------------------
El enfoque "área_retal <= área_disponible" falla siempre que las dimensiones
importen:

    Repisa 2.00 × 1.00 m      Retal A 1.00 × 1.50 m  (1.50 m²)
                              Retal B 0.20 × 7.50 m  (1.50 m²)

Ambos tienen menos área que la repisa y ninguno cabe. Aquí se usa
`core.packing`, que exige una posición real libre.

Criterio de selección entre repisas válidas
-------------------------------------------
Ordena por la menor desperdicio: la repisa que deja más área libre gana. Es
determinista (el desempate es por id) y, en la práctica, agrupa las piezas
parecidas Leaving hueco fragmented en vez de dispersarlas.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from core.entities import AllocationProposal, Scrap, ScrapDestination, Shelf
from core.packing import compute_occupancy, fits_single, place_in_bin

logger = logging.getLogger(__name__)

_EPOCH = datetime.min


@dataclass(frozen=True)
class _Placement:
    """Colocación candidata con su métrica de calidad (para ordenar)."""
    shelf: Shelf
    x: float
    y: float
    rotated: bool
    free_area_m2: float
    piece_count: int

    @property
    def sort_key(self) -> tuple[float, int, int]:
        # Menos espacio libre ganado = mejor encaje; por eso el signo negativo.
        # Los desempates (nº de piezas, id) garantizan determinismo.
        return (-self.free_area_m2, self.piece_count, self.shelf.id or 0)

_EPOCH = datetime.min


@dataclass(frozen=True)
class _Placement:
    """Colocación candidata con su métrica de calidad (para ordenar)."""
    shelf: Shelf
    x: float
    y: float
    rotated: bool
    free_area_m2: float
    piece_count: int

    @property
    def sort_key(self) -> tuple[float, int, int]:
        # Menos espacio libre ganado = mejor encaje; por eso el signo negativo.
        # Los desempates (nº de piezas, id) garantizan determinismo.
        return (-self.free_area_m2, self.piece_count, self.shelf.id or 0)


class AllocationService:
    """Busca la repisa compatible con más espacio libre."""

    def __init__(
        self,
        shelf_repo=None,
        scrap_repo=None,
        auto_recycle_sin_ubicacion: bool = False,
    ) -> None:
        self._shelves = shelf_repo
        self._scraps = scrap_repo
        self._auto_recycle = auto_recycle_sin_ubicacion

    def set_auto_recycle(self, enabled: bool) -> None:
        """Activa/desactiva el envío a reciclaje de lo que no encuentra hueco."""
        self._auto_recycle = enabled

    # ─── API principal ────────────────────────────────────────────────────────

    def propose(
        self,
        scrap: Scrap,
        shelves: Optional[list[Shelf]] = None,
    ) -> AllocationProposal:
        """
        Busca la mejor ubicación para un retal.

        Args:
            scrap:   Retal ya clasificado (reutilizable o reciclable).
            shelves: Candidatas. Si es None, se leen del repositorio.

        Returns:
            AllocationProposal con la repisa elegida, o el motivo por el que no
            se encontró ninguna. `rejected` recoge el detalle de cada repisa
            descartada, para que el usuario entienda el resultado.
        """
        if scrap.destination == ScrapDestination.RECICLABLE:
            return AllocationProposal(
                shelf=None,
                reason="El retal está destinado a reciclaje, no requiere ubicación.",
            )

        if shelves is None:
            if self._shelves is None:
                return AllocationProposal(
                    shelf=None, reason="No hay repositorio de repisas configurado."
                )
            shelves = self._shelves.get_all()

        if not shelves:
            return AllocationProposal(
                shelf=None,
                reason="No hay repisas registradas en el almacén. "
                       "Vaya a la pestaña Almacén para crear una.",
            )

        placements: list[_Placement] = []
        rejected: list[tuple[str, str]] = []

        for shelf in shelves:
            ok, reason = self._check_rules(scrap, shelf)
            if not ok:
                rejected.append((shelf.location_text, reason))
                continue

            placed = self._placed_rects(shelf.id)
            w, h = scrap.width_m, scrap.length_m

            if not fits_single(w, h, shelf.width_m, shelf.length_m):
                rejected.append((
                    shelf.location_text,
                    f"no cabe: {max(w, h):.2f}×{min(w, h):.2f} m no entra en "
                    f"{shelf.width_m:.2f}×{shelf.length_m:.2f} m",
                ))
                continue

            pos = place_in_bin(w, h, shelf.width_m, shelf.length_m, placed)
            if pos is None:
                rejected.append((
                    shelf.location_text,
                    "no se encontró una posición libre en la repisa",
                ))
                continue

            x, y, rotated = pos
            metrics = compute_occupancy(placed, shelf.width_m, shelf.length_m)
            placements.append(_Placement(
                shelf=shelf, x=x, y=y, rotated=rotated,
                free_area_m2=metrics["available_area_m2"],
                piece_count=len(placed),
            ))

        if not placements:
            detail = "; ".join(f"{loc}: {why}" for loc, why in rejected[:4])
            if len(rejected) > 4:
                detail += f" (y {len(rejected) - 4} más)"
            return AllocationProposal(
                shelf=None,
                rejected=rejected,
                reason=(
                    "No se encontró una ubicación física compatible. "
                    f"Motivos: {detail}" if detail else
                    "No se encontró una ubicación física compatible."
                ),
                is_confident=False,
            )

        best = min(placements, key=lambda p: p.sort_key)
        logger.info(
            "Retal asignado a %s en (%.2f, %.2f)%s",
            best.shelf.location_text, best.x, best.y,
            " rotado 90°" if best.rotated else "",
        )
        return AllocationProposal(
            shelf=best.shelf,
            rotated=best.rotated,
            position_x_m=best.x,
            position_y_m=best.y,
            reason="Cumple las reglas de la repisa y existe espacio físico libre.",
            rejected=rejected,
            is_confident=True,
        )

    def destination_for(
        self,
        scrap: Scrap,
        proposal: AllocationProposal,
    ) -> ScrapDestination:
        """
        Decide el destino final teniendo en cuenta si se encontró ubicación.

        Si el usuario configuró `auto_recycle_sin_ubicacion`, un retal
        reutilizable que no cabe pasa a reciclaje. Si NO lo configuró (por
        defecto), el retal se conserva como REUTILIZABLE **sin ubicación**: es
        material valioso que no debe perderse solo porque hoy no cabe en ninguna
        repisa configurada.
        """
        if scrap.destination == ScrapDestination.RECICLABLE:
            return ScrapDestination.RECICLABLE
        if proposal.found:
            return ScrapDestination.REUTILIZABLE
        if self._auto_recycle:
            return ScrapDestination.RECICLABLE
        return ScrapDestination.REUTILIZABLE

    def append_no_location_reason(
        self,
        scrap: Scrap,
        proposal: AllocationProposal,
    ) -> list[str]:
        """Motivos a mostrar cuando no se halló ubicación."""
        reasons = list(scrap.reasons)
        reasons.append(proposal.reason or "Sin ubicación física disponible.")
        return reasons

    # ─── Interno ──────────────────────────────────────────────────────────────

    def _check_rules(self, scrap: Scrap, shelf: Shelf) -> tuple[bool, str]:
        """Valida las reglas configuradas de la repisa contra el retal."""
        r = shelf.rules

        if r.rejects_shape_family(scrap.shape):
            family = "irregulares" if scrap.shape.is_irregular_kind else "regulares"
            return False, f"solo admite formas {family}"

        reasons = r.dimension_reasons(scrap.width_m, scrap.length_m)
        if reasons:
            return False, reasons[0]

        reasons = r.area_reasons(scrap.area_m2)
        if reasons:
            return False, reasons[0]

        reasons = r.thickness_reasons(scrap.thickness_mm)
        if reasons:
            return False, reasons[0]

        return True, ""

    def _placed_rects(self, shelf_id: Optional[int]) -> list[tuple[float, float, float, float]]:
        """
        Rectángulos ya colocados en la repisa, como (x, y, w, h) en metros.

        La posición real de cada pieza se reconstruye ejecutando el mismo
        algoritmo de packing, en orden cronológico de alta. Es determinista, así
        que `place_in_bin` siempre encuentra el mismo hueco que se le ofreció
        cuando la pieza se asignó.

        Si el repositorio no está disponible, devuelve la lista vacía: el
        servicio degrada a "repisa vacía" en lugar de fallar.
        """
        if self._shelves is None or self._scraps is None or shelf_id is None:
            return []
        try:
            shelf = self._shelves.get_by_id(shelf_id)
            if shelf is None:
                return []
            placed: list[tuple[float, float, float, float]] = []
            items = sorted(
                self._scraps.get_by_shelf(shelf_id),
                key=lambda s: (s.created_at or _EPOCH, s.id or 0),
            )
            for s in items:
                if s.destination != ScrapDestination.REUTILIZABLE:
                    continue
                pos = place_in_bin(
                    s.width_m, s.length_m, shelf.width_m, shelf.length_m, placed
                )
                if pos is not None:
                    x, y, rotated = pos
                    w, h = (s.length_m, s.width_m) if rotated else (s.width_m, s.length_m)
                    placed.append((x, y, w, h))
            return placed
        except Exception as exc:  # pragma: no cover — defensivo
            logger.warning("No se pudo reconstruir la ocupación de la repisa %s: %s", shelf_id, exc)
            return []
