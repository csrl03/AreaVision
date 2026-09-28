"""
Repositorios de acceso a datos.

Todas las queries usan placeholders '?' para prevenir inyección SQL.
Los nombres de archivo de imágenes se generan por timestamp
(nunca basados en input del usuario) para prevenir path traversal.
"""
from __future__ import annotations

import io
import logging
import os
from datetime import datetime
from typing import Optional

import cv2
import numpy as np
from PIL import Image

from core.constants import SILHOUETTE_MAX_SIZE_PX, SILHOUETTE_PNG_COMPRESS
from core.entities import Measurement, MeasurementCategory
from core.exceptions import StorageError
from config import IMAGES_DIR
from data.database import DatabaseManager

logger = logging.getLogger(__name__)


class MeasurementRepository:
    """CRUD para mediciones en SQLite."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    # ─── Escritura ─────────────────────────────────────────────────────────────

    def save(self, measurement: Measurement) -> int:
        """Inserta una medición y retorna el ID generado."""
        sql = """
        INSERT INTO measurements
            (name, area_pixels, area_m2, category, factor_k_used, distance_cm,
             timestamp, notes, silhouette_path, perimeter_pixels, circularity,
             confidence, is_valid, scrap_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            with self._db.get_connection() as conn:
                cursor = conn.execute(sql, (
                    measurement.name,
                    measurement.area_pixels,
                    measurement.area_m2,
                    measurement.category.value,
                    measurement.factor_k_used,
                    measurement.distance_cm,
                    measurement.timestamp.isoformat(),
                    measurement.notes,
                    measurement.silhouette_path,
                    measurement.perimeter_pixels,
                    measurement.circularity,
                    measurement.confidence,
                    int(measurement.is_valid),
                    measurement.scrap_id,
                ))
                conn.commit()
                new_id: int = cursor.lastrowid
            logger.info("Medición guardada con ID=%d", new_id)
            return new_id
        except Exception as exc:
            raise StorageError(f"Error al guardar medición: {exc}") from exc

    def delete(self, measurement_id: int) -> bool:
        """Elimina la medición y su imagen asociada si existe. Retorna True si existía."""
        m = self.get_by_id(measurement_id)
        if m and m.silhouette_path and os.path.exists(m.silhouette_path):
            try:
                os.remove(m.silhouette_path)
            except OSError:
                logger.warning("No se pudo eliminar la imagen: %s", m.silhouette_path)

        with self._db.get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM measurements WHERE id = ?", (measurement_id,)
            )
            conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info("Medición ID=%d eliminada", measurement_id)
        return deleted

    def delete_all(self) -> int:
        """Elimina todas las mediciones y sus imágenes. Retorna el conteo."""
        for m in self.get_all():
            if m.silhouette_path and os.path.exists(m.silhouette_path):
                try:
                    os.remove(m.silhouette_path)
                except OSError:
                    pass
        with self._db.get_connection() as conn:
            cursor = conn.execute("DELETE FROM measurements")
            conn.commit()
        logger.info("Se eliminaron %d mediciones", cursor.rowcount)
        return cursor.rowcount

    # ─── Lectura ───────────────────────────────────────────────────────────────

    def get_all(self) -> list[Measurement]:
        """Devuelve todas las mediciones, más recientes primero."""
        with self._db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM measurements ORDER BY timestamp DESC"
            ).fetchall()
        return [self._row_to_entity(r) for r in rows]

    def get_by_id(self, measurement_id: int) -> Optional[Measurement]:
        with self._db.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM measurements WHERE id = ?", (measurement_id,)
            ).fetchone()
        return self._row_to_entity(row) if row else None

    def search_by_name(self, query: str) -> list[Measurement]:
        """Búsqueda case-insensitive por nombre (coincidencia parcial)."""
        with self._db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM measurements WHERE name LIKE ? ORDER BY timestamp DESC",
                (f"%{query}%",),
            ).fetchall()
        return [self._row_to_entity(r) for r in rows]

    def filter_by_category(self, category: MeasurementCategory) -> list[Measurement]:
        with self._db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM measurements WHERE category = ? ORDER BY timestamp DESC",
                (category.value,),
            ).fetchall()
        return [self._row_to_entity(r) for r in rows]

    def get_statistics(self) -> dict:
        sql = """
        SELECT
            COUNT(*)        AS total,
            AVG(area_m2)    AS avg_area,
            MIN(area_m2)    AS min_area,
            MAX(area_m2)    AS max_area,
            SUM(area_m2)    AS total_area
        FROM measurements WHERE is_valid = 1
        """
        with self._db.get_connection() as conn:
            row = conn.execute(sql).fetchone()
        return dict(row) if row else {}

    def export_csv(self) -> str:
        """Serializa todas las mediciones como texto CSV."""
        headers = [
            "id", "nombre", "area_m2", "area_cm2", "categoria",
            "factorK", "distancia_cm", "timestamp", "notas",
        ]
        rows = self.get_all()
        lines = [",".join(headers)]
        for m in rows:
            lines.append(",".join([
                str(m.id or ""),
                (m.name or "").replace(",", ";"),
                f"{m.area_m2:.6f}",
                f"{m.area_cm2:.4f}",
                m.category.value,
                f"{m.factor_k_used:.4e}",
                str(m.distance_cm),
                m.timestamp.isoformat(),
                (m.notes or "").replace(",", ";"),
            ]))
        return "\n".join(lines)

    # ─── Conversión ───────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_entity(row: sqlite3.Row) -> Measurement:
        # `scrap_id` llegó en la migración v2. Se lee con `.keys()` para que una
        # fila de una base no migrada (o un SELECT explícito sin esa columna) no
        # rompa la lectura del historial antiguo.
        scrap_id = row["scrap_id"] if "scrap_id" in row.keys() else None
        return Measurement(
            id=row["id"],
            name=row["name"],
            area_pixels=row["area_pixels"],
            area_m2=row["area_m2"],
            category=MeasurementCategory(row["category"]),
            factor_k_used=row["factor_k_used"],
            distance_cm=row["distance_cm"],
            timestamp=datetime.fromisoformat(row["timestamp"]),
            notes=row["notes"],
            silhouette_path=row["silhouette_path"],
            perimeter_pixels=row["perimeter_pixels"],
            circularity=row["circularity"],
            confidence=row["confidence"],
            is_valid=bool(row["is_valid"]),
            scrap_id=scrap_id,
        )


class ImageStorageService:
    """Guarda y recupera imágenes de silueta en disco."""

    def __init__(self, images_dir: str = IMAGES_DIR) -> None:
        self._dir = images_dir
        os.makedirs(self._dir, exist_ok=True)

    def save_silhouette(self, frame_bgr: np.ndarray, timestamp: datetime) -> str:
        """
        Comprime y guarda la imagen de silueta.
        El nombre de archivo se genera por timestamp, nunca basado en input del usuario.

        Returns:
            Ruta absoluta al archivo PNG guardado.
        """
        # Redimensionar si supera el límite
        h, w = frame_bgr.shape[:2]
        if max(h, w) > SILHOUETTE_MAX_SIZE_PX:
            scale = SILHOUETTE_MAX_SIZE_PX / max(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            frame_bgr = cv2.resize(frame_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)

        # Convertir BGR → RGB y guardar como PNG
        pil_img = Image.fromarray(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
        filename = f"measurement_{timestamp.strftime('%Y%m%d_%H%M%S_%f')}.png"
        filepath = os.path.join(self._dir, filename)
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG", compress_level=SILHOUETTE_PNG_COMPRESS)
        with open(filepath, "wb") as f:
            f.write(buf.getvalue())
        logger.debug("Imagen guardada: %s (%d bytes)", filepath, buf.tell())
        return filepath
