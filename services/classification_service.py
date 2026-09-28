"""
Servicio de clasificación de retales — el pipeline de decisión de negocio.

    measurement
        ↓  geometry_analysis   (core.geometry)
        ↓  safety_analysis     (core.safety)
        ↓  thickness_validation (entrada manual; None = no capturado)
        ↓  reusability_classification
        ↓
    ScrapAnalysis  → REUTILIZABLE  o  RECICLABLE + lista de motivos

Reglas de diseño
----------------
- **Sin UI.** Este módulo no importa PyQt6. Es testeable de forma aislada y es
  el único lugar donde vive la decisión "esto se recicla".
- **Sin valores hardcodeados de negocio.** Todos los umbrales entran por
  `ReusePolicy`, que la UI rellena desde `settings.json`.
- **Motivos explícitos.** El usuario siempre puede ver *por qué* una pieza fue a
  reciclaje, como pide el flujo de negocio.
- **Degradación elegante.** Si el contorno no está disponible (porque
  `ProcessingResult` no lo expone, p. ej. una app externa que no lo setea), se
  construye un `GeometryAnalysis` con los valores que sí connu y el análisis
  continúa en vez de romperse.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

from core.entities import (
    GeometryAnalysis,
    Regularity,
    ScrapAnalysis,
    ScrapDestination,
    ShapeType,
    SharpnessReport,
)
from core.geometry import analyze_contour
from core.safety import analyze_sharpness
from core.scoring import compute_estimated_value

logger = logging.getLogger(__name__)

# Valores por defecto. Todos editables desde Configuración.
DEFAULT_POLICY = {
    "cost_per_m2_sheet": 85_000.0,
    "min_reusable_area_m2": 0.25,
    "max_reusable_area_m2": 0.0,          # 0 = sin máximo
    "min_reusable_thickness_mm": 2.0,
    "min_regularity_score": 0.70,
    "sharpness_alert_threshold": 0.55,
    "regular_at": 0.92,
    "irregular_below": 0.75,
    "simplify_ratio": 0.02,
}


@dataclass
class ReusePolicy:
    """
    Parámetros de negocio de la clasificación de retales.

    Se construye desde `settings.json`; los valores ausentes caen al
    default. Ninguna regla de negocio está escrita en el cuerpo del servicio.
    """
    cost_per_m2_sheet: float = DEFAULT_POLICY["cost_per_m2_sheet"]
    min_reusable_area_m2: float = DEFAULT_POLICY["min_reusable_area_m2"]
    max_reusable_area_m2: float = DEFAULT_POLICY["max_reusable_area_m2"]
    min_reusable_thickness_mm: float = DEFAULT_POLICY["min_reusable_thickness_mm"]
    min_regularity_score: float = DEFAULT_POLICY["min_regularity_score"]
    sharpness_alert_threshold: float = DEFAULT_POLICY["sharpness_alert_threshold"]
    regular_at: float = DEFAULT_POLICY["regular_at"]
    irregular_below: float = DEFAULT_POLICY["irregular_below"]
    simplify_ratio: float = DEFAULT_POLICY["simplify_ratio"]

    @classmethod
    def from_settings(cls, cfg: dict) -> "ReusePolicy":
        """Construye la política desde un dict de `settings.json` (o de tests)."""
        d = DEFAULT_POLICY
        return cls(
            cost_per_m2_sheet=float(cfg.get("cost_per_m2_sheet", d["cost_per_m2_sheet"])),
            min_reusable_area_m2=float(cfg.get("min_reusable_area_m2", d["min_reusable_area_m2"])),
            max_reusable_area_m2=float(cfg.get("max_reusable_area_m2", d["max_reusable_area_m2"])),
            min_reusable_thickness_mm=float(
                cfg.get("min_reusable_thickness_mm", d["min_reusable_thickness_mm"])),
            min_regularity_score=float(cfg.get("min_regularity_score", d["min_regularity_score"])),
            sharpness_alert_threshold=float(
                cfg.get("sharpness_alert_threshold", d["sharpness_alert_threshold"])),
            regular_at=float(cfg.get("regular_at", d["regular_at"])),
            irregular_below=float(cfg.get("irregular_below", d["irregular_below"])),
            simplify_ratio=float(cfg.get("dxf_simplify_epsilon_ratio", d["simplify_ratio"])),
        )


class ClassificationService:
    """Orquesta geometría → seguridad → decisión de reutilización."""

    def __init__(self, policy: Optional[ReusePolicy] = None) -> None:
        self._policy = policy or ReusePolicy()

    @property
    def policy(self) -> ReusePolicy:
        return self._policy

    def set_policy(self, policy: ReusePolicy) -> None:
        self._policy = policy

    # ─── Pipeline ─────────────────────────────────────────────────────────────

    def analyze(
        self,
        contour: Optional[np.ndarray],
        factor_k: float,
        area_m2: float,
        thickness_mm: Optional[float] = None,
    ) -> Optional[ScrapAnalysis]:
        """
        Ejecuta el pipeline completo de clasificación.

        Args:
            contour:    Contorno Nx1x2 de OpenCV. Puede ser None.
            factor_k:   FactorK vigente (m²/px²).
            area_m2:    Área ya calibrada en m².
            thickness_mm: Espesor en mm, o None si el usuario aún no lo captura.

        Returns:
            ScrapAnalysis, o None si no hay ni contorno ni FactorK utilizable.
        """
        geometry = self._analyze_geometry(contour, factor_k, area_m2)
        if geometry is None:
            return None

        safety = self._analyze_safety(contour)
        destination, reasons = self._decide(geometry, safety, thickness_mm)
        value = compute_estimated_value(geometry.area_m2, self._policy.cost_per_m2_sheet)

        return ScrapAnalysis(
            geometry=geometry,
            safety=safety,
            destination=destination,
            estimated_value=value,
            reasons=reasons,
            thickness_mm=thickness_mm,
            cost_per_m2=self._policy.cost_per_m2_sheet,
        )

    # ─── Pasos ────────────────────────────────────────────────────────────────

    def _analyze_geometry(
        self,
        contour: Optional[np.ndarray],
        factor_k: float,
        area_m2: float,
    ) -> Optional[GeometryAnalysis]:
        if contour is not None and factor_k > 0:
            result = analyze_contour(
                contour,
                factor_k,
                simplify_ratio=self._policy.simplify_ratio,
                regular_at=self._policy.regular_at,
                irregular_below=self._policy.irregular_below,
            )
            if result is not None:
                return result

        # Degradación: sin contorno no hay forma ni dimensiones, pero sí se puede
        # decidir por área. Se construye un análisis con lo que sí sabemos.
        if area_m2 <= 0:
            return None
        logger.debug("Sin contorno utilizable: se clasifica solo por área (%.4f m²)", area_m2)
        side = (area_m2) ** 0.5
        return GeometryAnalysis(
            shape=ShapeType.OTRA,
            regularity=Regularity.SEMI_REGULAR,
            regularity_score=0.0,
            confidence=0.0,
            width_m=side,
            length_m=side,
            vertex_count=0,
            circularity=0.0,
            solidity=0.0,
            convexity_defects=0,
            area_m2=area_m2,
        )

    def _analyze_safety(self, contour: Optional[np.ndarray]) -> SharpnessReport:
        if contour is not None:
            report = analyze_sharpness(
                contour, threshold=self._policy.sharpness_alert_threshold
            )
            if report is not None:
                return report
        # Sin contorno no hay evidencia de riesgo: no se dispara la alerta.
        # Es importante no generar falsos positivos por ausencia de datos.
        return SharpnessReport(
            score=0.0,
            min_internal_angle_deg=180.0,
            protrusion_depth=0.0,
            spike_factor=0.0,
            convexity_defect_ratio=0.0,
            local_aspect=1.0,
            triggered=False,
        )

    def _decide(
        self,
        geometry: GeometryAnalysis,
        safety: SharpnessReport,
        thickness_mm: Optional[float],
    ) -> tuple[ScrapDestination, list[str]]:
        """
        Aplica las reglas de negocio y devuelve (destino, motivos).

        Los motivos son de dos tipos, y la UI los distingue por el color del
        destino: los que justifican el reciclaje y, si aplica, los que="{%s %}"
        confirman por qué la pieza SÍ es reutilizable.
        """
        p = self._policy
        recycle: list[str] = []
        reuse: list[str] = []

        # ── Área ──
        if geometry.area_m2 < p.min_reusable_area_m2:
            recycle.append(
                f"Área inferior al mínimo reutilizable "
                f"({geometry.area_m2:.3f} < {p.min_reusable_area_m2:.2f} m²)."
            )
        else:
            reuse.append(f"Cumple el área mínima reutilizable ({geometry.area_m2:.3f} m²).")
        if p.max_reusable_area_m2 > 0 and geometry.area_m2 > p.max_reusable_area_m2:
            recycle.append(
                f"Área superior al máximo reutilizable "
                f"({geometry.area_m2:.3f} > {p.max_reusable_area_m2:.2f} m²)."
            )

        # ── Espesor ──
        if thickness_mm is None:
            # No bloquea: el usuario puede no conocerlo. Se deja constancia.
            reuse.append("Espesor no capturado (no evaluado).")
        elif thickness_mm < p.min_reusable_thickness_mm:
            recycle.append(
                f"Espesor inferior al mínimo ({thickness_mm:.1f} < "
                f"{p.min_reusable_thickness_mm:.1f} mm)."
            )
        else:
            reuse.append(f"Cumple el espesor mínimo ({thickness_mm:.1f} mm).")

        # ── Regularidad ──
        if geometry.is_degraded:
            # No hay contorno, así que la regularidad es DESCONOCIDA, no mala.
            # Aplicar aquí el umbral mandaría a reciclaje piezas perfectamente
            # buenas solo porque faltó el dato: "no lo sé" no es "es irregular".
            reuse.append("Forma no analizada (sin contorno disponible); regularidad no evaluada.")
        elif geometry.regularity_score < p.min_regularity_score:
            recycle.append(
                f"Forma demasiado irregular (regularidad {geometry.regularity_score:.2f} < "
                f"{p.min_regularity_score:.2f})."
            )
        else:
            reuse.append(
                f"Regularidad suficiente ({geometry.regularity_score:.2f} ≥ "
                f"{p.min_regularity_score:.2f})."
            )

        if recycle:
            return ScrapDestination.RECICLABLE, recycle
        return ScrapDestination.REUTILIZABLE, reuse
