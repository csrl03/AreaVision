"""
Repositorio de configuración de usuario.

Lee y escribe data/settings.json para persistir preferencias entre sesiones sin
necesidad de reiniciar la aplicación.

Estructura de settings.json
─────────────────────────────
{
  "min_contour_area_pixels": 500,
  "detection_sensitivity": "media",
  "category_thresholds": {
    "A": [0.0, 1.0],
    "B": [1.0, 2.0],
    "C": [2.0, 3.0],
    "D": [3.0, 4.0]
  },
  "cost_per_m2_sheet": 85000.0,
  "currency_symbol": "$",
  "min_reusable_area_m2": 0.25,
  "max_reusable_area_m2": 0.0,
  "min_reusable_thickness_mm": 2.0,
  "min_regularity_score": 0.70,
  "sharpness_alert_threshold": 0.55,
  "auto_recycle_sin_ubicacion": false,
  "dxf_simplify_epsilon_ratio": 0.02
}
"""
from __future__ import annotations

import copy
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# ── Valores por defecto ───────────────────────────────────────────────────────
_DEFAULTS: dict[str, Any] = {
    "min_contour_area_pixels": 2000,
    "detection_sensitivity": "baja",
    "category_thresholds": {
        "A": [0.0, 1.0],
        "B": [1.0, 2.0],
        "C": [2.0, 3.0],
        "D": [3.0, 4.0],
    },
    # ── Gestión de retales (añadido en v2) ──
    # `max_reusable_area_m2 = 0.0` significa "sin máximo", igual que en
    # ShelfRules: un 0 no es un área válida de retal, así que es un centinela
    # seguro para "ilimitado".
    "cost_per_m2_sheet": 85_000.0,
    "currency_code": "COP",
    "currency_symbol": "$",
    "min_reusable_area_m2": 0.25,
    "max_reusable_area_m2": 0.0,
    "min_reusable_thickness_mm": 2.0,
    "min_regularity_score": 0.70,
    "sharpness_alert_threshold": 0.55,
    "auto_recycle_sin_ubicacion": False,
    "dxf_simplify_epsilon_ratio": 0.02,
}

# ── Parámetros OpenCV por nivel de sensibilidad ───────────────────────────────
# adaptive_c  : constante sustraída a la media; mayor = menos sensible (más C = ignora más detalles)
# block_size  : vecindario de umbralización; mayor = capta formas globales, ignora texturas finas
SENSITIVITY_PARAMS: dict[str, dict[str, int]] = {
    "alta":  {"adaptive_c": 2,  "block_size": 11},   # muy sensible, capta todo
    "media": {"adaptive_c": 8,  "block_size": 21},   # balance
    "baja":  {"adaptive_c": 18, "block_size": 41},   # ignora sombras y texturas
    "macro": {"adaptive_c": 26, "block_size": 61},   # solo formas grandes y sólidas
}


class SettingsRepository:
    """
    Persiste y carga la configuración del usuario en un archivo JSON.

    Uso típico:
        repo = SettingsRepository(path="data/settings.json")
        cfg  = repo.load()          # carga o crea con defaults
        repo.save({...})            # valida y guarda
        cfg  = repo.get()           # retorna la configuración en memoria
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._data: dict[str, Any] = {}

    # ── API pública ───────────────────────────────────────────────────────────

    def load(self) -> dict[str, Any]:
        """
        Carga la configuración desde disco.
        Si el archivo no existe o está malformado, usa los valores por defecto.
        Siempre rellena claves faltantes con defaults.
        """
        if os.path.exists(self._path):
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                # Merge superficial con defaults para claves nuevas.
                # `deepcopy` es necesario: un `dict(_DEFAULTS)` comparte los
                # sub-diccionarios, así que mutarlos contaminaría los defaults
                # de toda la aplicación.
                merged: dict[str, Any] = copy.deepcopy(_DEFAULTS)
                merged.update(loaded)
                # Merge anidado para category_thresholds
                if isinstance(loaded.get("category_thresholds"), dict):
                    merged["category_thresholds"] = {
                        **_DEFAULTS["category_thresholds"],
                        **loaded["category_thresholds"],
                    }
                self._data = self._validate(merged)
            except (json.JSONDecodeError, OSError, KeyError) as exc:
                logger.warning(
                    "No se pudo leer settings.json (%s). Usando valores por defecto.", exc
                )
                self._data = copy.deepcopy(_DEFAULTS)
        else:
            self._data = copy.deepcopy(_DEFAULTS)
        return self._data

    def save(self, data: dict[str, Any]) -> None:
        """
        Valida los datos y los guarda en disco.

        Raises:
            OSError: Si no se puede escribir el archivo.
            ValueError: Si los datos no pasan la validación.
        """
        validated = self._validate(data)
        self._data = validated
        try:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(validated, f, indent=2, ensure_ascii=False)
            logger.info("Configuración guardada en %s", self._path)
        except OSError as exc:
            logger.error("No se pudo guardar settings.json: %s", exc)
            raise

    def get(self) -> dict[str, Any]:
        """Retorna la configuración actual en memoria (carga si aún no se ha llamado load)."""
        if not self._data:
            self.load()
        return self._data

    # ── Validación ────────────────────────────────────────────────────────────

    @staticmethod
    def _validate(data: dict[str, Any]) -> dict[str, Any]:
        """
        Valida y normaliza todos los campos.
        Valores inválidos se reemplazan por sus defaults silenciosamente.
        """
        out: dict[str, Any] = {}

        # ── min_contour_area_pixels — entero ≥ 1 ─────────────────────────────
        raw_px = data.get("min_contour_area_pixels", _DEFAULTS["min_contour_area_pixels"])
        try:
            px = int(raw_px)
            if px < 1:
                raise ValueError("debe ser ≥ 1")
        except (ValueError, TypeError):
            px = int(_DEFAULTS["min_contour_area_pixels"])
        out["min_contour_area_pixels"] = px

        # ── detection_sensitivity — solo valores del catálogo ─────────────────
        sens = data.get("detection_sensitivity", _DEFAULTS["detection_sensitivity"])
        if sens not in SENSITIVITY_PARAMS:
            sens = _DEFAULTS["detection_sensitivity"]
        out["detection_sensitivity"] = sens

        # ── category_thresholds — 4 rangos encadenados, estrictamente ascendentes
        raw_thresh = data.get("category_thresholds", _DEFAULTS["category_thresholds"])
        cats = ["A", "B", "C", "D"]
        uppers: list[float] = []
        valid = True
        prev: float = 0.0

        for cat in cats:
            raw_range = raw_thresh.get(cat, _DEFAULTS["category_thresholds"][cat])
            try:
                upper = float(raw_range[1])
                if upper <= prev or upper <= 0:
                    logger.warning(
                        "Umbral de categoría %s inválido (%.4f ≤ %.4f). Usando defaults.", cat, upper, prev
                    )
                    valid = False
                    break
                uppers.append(upper)
                prev = upper
            except (IndexError, TypeError, ValueError):
                logger.warning("Umbral de categoría %s malformado. Usando defaults.", cat)
                valid = False
                break

        if valid and len(uppers) == 4:
            thresholds: dict[str, list[float]] = {
                "A": [0.0,      uppers[0]],
                "B": [uppers[0], uppers[1]],
                "C": [uppers[1], uppers[2]],
                "D": [uppers[2], uppers[3]],
            }
        else:
            thresholds = dict(_DEFAULTS["category_thresholds"])

        out["category_thresholds"] = thresholds

        # ── Gestión de retales ────────────────────────────────────────────────
        # Cada valor se valida por separado y cae al default en silencio con un
        # warning, siguiendo la misma política defensiva del resto del archivo.
        out["cost_per_m2_sheet"] = SettingsRepository._num(
            data, "cost_per_m2_sheet", _DEFAULTS["cost_per_m2_sheet"], minimum=0.0
        )
        out["min_reusable_area_m2"] = SettingsRepository._num(
            data, "min_reusable_area_m2", _DEFAULTS["min_reusable_area_m2"], minimum=0.0
        )
        # El máximo 0 es el centinela "sin límite": se preserva tal cual.
        out["max_reusable_area_m2"] = SettingsRepository._num(
            data, "max_reusable_area_m2", _DEFAULTS["max_reusable_area_m2"], minimum=0.0
        )
        out["min_reusable_thickness_mm"] = SettingsRepository._num(
            data, "min_reusable_thickness_mm", _DEFAULTS["min_reusable_thickness_mm"], minimum=0.0
        )
        out["min_regularity_score"] = SettingsRepository._num(
            data, "min_regularity_score", _DEFAULTS["min_regularity_score"],
            minimum=0.0, maximum=1.0,
        )
        out["sharpness_alert_threshold"] = SettingsRepository._num(
            data, "sharpness_alert_threshold", _DEFAULTS["sharpness_alert_threshold"],
            minimum=0.0, maximum=1.0,
        )
        out["dxf_simplify_epsilon_ratio"] = SettingsRepository._num(
            data, "dxf_simplify_epsilon_ratio", _DEFAULTS["dxf_simplify_epsilon_ratio"],
            minimum=0.001, maximum=0.2,
        )

        symbol = str(data.get("currency_symbol", _DEFAULTS["currency_symbol"])).strip()
        out["currency_symbol"] = symbol[:4] if symbol else _DEFAULTS["currency_symbol"]
        out["currency_code"] = str(
            data.get("currency_code", _DEFAULTS["currency_code"])
        ).strip().upper()[:6] or _DEFAULTS["currency_code"]

        out["auto_recycle_sin_ubicacion"] = bool(
            data.get("auto_recycle_sin_ubicacion", _DEFAULTS["auto_recycle_sin_ubicacion"])
        )
        return out

    @staticmethod
    def _num(
        data: dict[str, Any],
        key: str,
        default: float,
        minimum: float | None = None,
        maximum: float | None = None,
    ) -> float:
        """Lee un float acotado. Valores fuera de rango caen al default."""
        try:
            value = float(data.get(key, default))
        except (TypeError, ValueError):
            logger.warning("Ajuste '%s' no es numérico. Usando %s.", key, default)
            return float(default)
        if minimum is not None and value < minimum:
            logger.warning("Ajuste '%s' = %s < %s. Usando %s.", key, value, minimum, default)
            return float(default)
        if maximum is not None and value > maximum:
            logger.warning("Ajuste '%s' = %s > %s. Usando %s.", key, value, maximum, default)
            return float(default)
        return value
