"""
Repositorios del almacén de retales.

Mismo estilo y convenciones que `data/repositories.py`:
- placeholders '?' exclusivamente (nunca f-strings con datos de usuario);
- un repositorio por tabla;
- un `_row_to_entity` estático al final de cada clase;
- `with self._db.get_connection() as conn:` + `conn.commit()` explícito.

Las consultas de `ShelfRepository` y `ScrapRepository` usan LEFT JOIN para
traer el nombre del estante y de la repisa, de modo que la UI pueda pintar
"Estante 1 / Repisa 2" sin un segundo viaje a la base por cada fila.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from typing import Optional

from core.entities import (
    Regularity,
    Scrap,
    ScrapDestination,
    ScrapStatus,
    Shelf,
    ShelfRules,
    ShapeType,
    StorageArea,
)
from core.exceptions import StorageError

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now().isoformat()


def _opt(value) -> Optional[float]:
    """Normaliza 0 → None para que los rangos abiertos se guarden como NULL."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f <= 0 else f


class StorageAreaRepository:
    """CRUD de estantes."""

    def __init__(self, db) -> None:
        self._db = db

    def save(self, area: StorageArea) -> int:
        sql = "INSERT INTO storage_areas (name, description, created_at) VALUES (?, ?, ?)"
        try:
            with self._db.get_connection() as conn:
                cur = conn.execute(
                    sql,
                    (area.name, area.description, area.created_at.isoformat() if area.created_at else _now_iso()),
                )
                conn.commit()
                new_id: int = cur.lastrowid
            area.id = new_id
            logger.info("Estante guardado con ID=%d", new_id)
            return new_id
        except Exception as exc:
            raise StorageError(f"Error al guardar el estante: {exc}") from exc

    def update(self, area: StorageArea) -> bool:
        sql = "UPDATE storage_areas SET name = ?, description = ? WHERE id = ?"
        try:
            with self._db.get_connection() as conn:
                cur = conn.execute(sql, (area.name, area.description, area.id))
                conn.commit()
            return cur.rowcount > 0
        except Exception as exc:
            raise StorageError(f"Error al actualizar el estante: {exc}") from exc

    def delete(self, area_id: int) -> bool:
        """
        Elimina el estante. `ON DELETE CASCADE` borra sus repisas, y a su vez
        `scraps.shelf_id` queda en NULL (no se borra el retal: perder la
        ubicación de una pieza ya medida sería peor que dejar el hueco libre).
        """
        try:
            with self._db.get_connection() as conn:
                cur = conn.execute("DELETE FROM storage_areas WHERE id = ?", (area_id,))
                conn.commit()
            deleted = cur.rowcount > 0
            if deleted:
                logger.info("Estante ID=%d eliminado (repisas en cascada)", area_id)
            return deleted
        except Exception as exc:
            raise StorageError(f"Error al eliminar el estante: {exc}") from exc

    def get_all(self) -> list[StorageArea]:
        with self._db.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM storage_areas ORDER BY name COLLATE NOCASE"
            ).fetchall()
        return [self._row_to_entity(r) for r in rows]

    def get_by_id(self, area_id: int) -> Optional[StorageArea]:
        with self._db.get_connection() as conn:
            row = conn.execute("SELECT * FROM storage_areas WHERE id = ?", (area_id,)).fetchone()
        return self._row_to_entity(row) if row else None

    def count(self) -> int:
        with self._db.get_connection() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM storage_areas").fetchone()[0])

    @staticmethod
    def _row_to_entity(row: sqlite3.Row) -> StorageArea:
        return StorageArea(
            id=row["id"],
            name=row["name"],
            description=row["description"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
        )


class ShelfRepository:
    """CRUD de repisas, con ocupación calculada."""

    def __init__(self, db) -> None:
        self._db = db

    def save(self, shelf: Shelf) -> int:
        sql = """
        INSERT INTO shelves
            (storage_area_id, name, width_m, length_m,
             accepts_regular, accepts_irregular,
             min_width_m, max_width_m, min_length_m, max_length_m,
             min_area_m2, max_area_m2, min_thickness_mm, max_thickness_mm,
             created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            with self._db.get_connection() as conn:
                cur = conn.execute(sql, self._params(shelf))
                conn.commit()
                new_id: int = cur.lastrowid
            shelf.id = new_id
            logger.info("Repisa guardada con ID=%d", new_id)
            return new_id
        except Exception as exc:
            raise StorageError(f"Error al guardar la repisa: {exc}") from exc

    def update(self, shelf: Shelf) -> bool:
        sql = """
        UPDATE shelves SET
            storage_area_id = ?, name = ?, width_m = ?, length_m = ?,
            accepts_regular = ?, accepts_irregular = ?,
            min_width_m = ?, max_width_m = ?, min_length_m = ?, max_length_m = ?,
            min_area_m2 = ?, max_area_m2 = ?, min_thickness_mm = ?, max_thickness_mm = ?
        WHERE id = ?
        """
        params = self._params(shelf) + (shelf.id,)
        try:
            with self._db.get_connection() as conn:
                cur = conn.execute(sql, params)
                conn.commit()
            return cur.rowcount > 0
        except Exception as exc:
            raise StorageError(f"Error al actualizar la repisa: {exc}") from exc

    def delete(self, shelf_id: int) -> bool:
        """Elimina la repisa; los retales que estaban en ella quedan sin ubicación."""
        try:
            with self._db.get_connection() as conn:
                cur = conn.execute("DELETE FROM shelves WHERE id = ?", (shelf_id,))
                conn.commit()
            return cur.rowcount > 0
        except Exception as exc:
            raise StorageError(f"Error al eliminar la repisa: {exc}") from exc

    def get_all(self) -> list[Shelf]:
        """Devuelve todas las repisas con su ocupación calculada."""
        with self._db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT s.*,
                       a.name AS area_name,
                       COALESCE(SUM(CASE WHEN sc.destination = 'REUTILIZABLE'
                                          AND sc.status != 'RECICLADO'
                                         THEN sc.area_m2 ELSE 0 END), 0) AS used_area,
                       COALESCE(SUM(CASE WHEN sc.destination = 'REUTILIZABLE'
                                          AND sc.status != 'RECICLADO'
                                         THEN 1 ELSE 0 END), 0)          AS scrap_count
                FROM shelves s
                JOIN storage_areas a ON a.id = s.storage_area_id
                LEFT JOIN scraps sc ON sc.shelf_id = s.id
                GROUP BY s.id
                ORDER BY a.name COLLATE NOCASE, s.name COLLATE NOCASE
                """
            ).fetchall()
        return [self._row_to_entity(r) for r in rows]

    def get_by_id(self, shelf_id: int) -> Optional[Shelf]:
        with self._db.get_connection() as conn:
            row = conn.execute(
                """
                SELECT s.*, a.name AS area_name,
                       COALESCE(SUM(CASE WHEN sc.destination = 'REUTILIZABLE'
                                          AND sc.status != 'RECICLADO'
                                         THEN sc.area_m2 ELSE 0 END), 0) AS used_area,
                       COALESCE(SUM(CASE WHEN sc.destination = 'REUTILIZABLE'
                                          AND sc.status != 'RECICLADO'
                                         THEN 1 ELSE 0 END), 0)          AS scrap_count
                FROM shelves s
                JOIN storage_areas a ON a.id = s.storage_area_id
                LEFT JOIN scraps sc ON sc.shelf_id = s.id
                WHERE s.id = ?
                GROUP BY s.id
                """,
                (shelf_id,),
            ).fetchone()
        return self._row_to_entity(row) if row else None

    def get_by_area(self, area_id: int) -> list[Shelf]:
        with self._db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT s.*, a.name AS area_name,
                       COALESCE(SUM(CASE WHEN sc.destination = 'REUTILIZABLE'
                                          AND sc.status != 'RECICLADO'
                                         THEN sc.area_m2 ELSE 0 END), 0) AS used_area,
                       COALESCE(SUM(CASE WHEN sc.destination = 'REUTILIZABLE'
                                          AND sc.status != 'RECICLADO'
                                         THEN 1 ELSE 0 END), 0)          AS scrap_count
                FROM shelves s
                JOIN storage_areas a ON a.id = s.storage_area_id
                LEFT JOIN scraps sc ON sc.shelf_id = s.id
                WHERE s.storage_area_id = ?
                GROUP BY s.id
                ORDER BY s.name COLLATE NOCASE
                """,
                (area_id,),
            ).fetchall()
        return [self._row_to_entity(r) for r in rows]

    def count(self) -> int:
        with self._db.get_connection() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM shelves").fetchone()[0])

    # ── Interno ──────────────────────────────────────────────────────────────

    def _params(self, shelf: Shelf) -> tuple:
        r: ShelfRules = shelf.rules
        return (
            shelf.storage_area_id,
            shelf.name,
            float(shelf.width_m),
            float(shelf.length_m),
            int(r.accepts_regular),
            int(r.accepts_irregular),
            _opt(r.min_width_m),
            _opt(r.max_width_m),
            _opt(r.min_length_m),
            _opt(r.max_length_m),
            _opt(r.min_area_m2),
            _opt(r.max_area_m2),
            _opt(r.min_thickness_mm),
            _opt(r.max_thickness_mm),
            shelf.created_at.isoformat() if shelf.created_at else _now_iso(),
        )

    @staticmethod
    def _row_to_entity(row: sqlite3.Row) -> Shelf:
        rules = ShelfRules(
            accepts_regular=bool(row["accepts_regular"]),
            accepts_irregular=bool(row["accepts_irregular"]),
            min_width_m=row["min_width_m"],
            max_width_m=row["max_width_m"],
            min_length_m=row["min_length_m"],
            max_length_m=row["max_length_m"],
            min_area_m2=row["min_area_m2"],
            max_area_m2=row["max_area_m2"],
            min_thickness_mm=row["min_thickness_mm"],
            max_thickness_mm=row["max_thickness_mm"],
        )
        return Shelf(
            id=row["id"],
            storage_area_id=row["storage_area_id"],
            name=row["name"],
            width_m=row["width_m"],
            length_m=row["length_m"],
            rules=rules,
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            used_area_m2=float(row["used_area"] or 0.0),
            scrap_count=int(row["scrap_count"] or 0),
            storage_area_name=row["area_name"] if "area_name" in row.keys() else None,
        )


class ScrapRepository:
    """CRUD del inventario de retales, con búsqueda para reutilización."""

    def __init__(self, db) -> None:
        self._db = db

    def save(self, scrap: Scrap) -> int:
        sql = """
        INSERT INTO scraps
            (measurement_id, name, area_m2, width_m, length_m, thickness_mm,
             shape, regularity, shape_confidence, regularity_score, vertex_count,
             shelf_id, storage_area_id, destination, status,
             sharpness_score, safety_alert, estimated_value, cost_per_m2,
             reasons, silhouette_path, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            with self._db.get_connection() as conn:
                cur = conn.execute(sql, self._params(scrap))
                conn.commit()
                new_id: int = cur.lastrowid
            scrap.id = new_id
            logger.info("Retal guardado con ID=%d", new_id)
            return new_id
        except Exception as exc:
            raise StorageError(f"Error al guardar el retal: {exc}") from exc

    def update(self, scrap: Scrap) -> bool:
        sql = """
        UPDATE scraps SET
            name = ?, thickness_mm = ?, shelf_id = ?, storage_area_id = ?,
            destination = ?, status = ?, estimated_value = ?, reasons = ?
        WHERE id = ?
        """
        try:
            with self._db.get_connection() as conn:
                cur = conn.execute(sql, (
                    scrap.name,
                    scrap.thickness_mm,
                    scrap.shelf_id,
                    scrap.storage_area_id,
                    scrap.destination.value,
                    scrap.status.value,
                    scrap.estimated_value,
                    json.dumps(scrap.reasons, ensure_ascii=False),
                    scrap.id,
                ))
                conn.commit()
            return cur.rowcount > 0
        except Exception as exc:
            raise StorageError(f"Error al actualizar el retal: {exc}") from exc

    def set_status(self, scrap_id: int, status: ScrapStatus) -> bool:
        """Cambia el estado del retal (DISPONIBLE → RESERVADO → UTILIZADO…)."""
        with self._db.get_connection() as conn:
            cur = conn.execute(
                "UPDATE scraps SET status = ? WHERE id = ?", (status.value, scrap_id)
            )
            conn.commit()
        return cur.rowcount > 0

    def assign_shelf(self, scrap_id: int, shelf: Optional[Shelf]) -> bool:
        """Asigna (o desasigna, con `shelf=None`) la ubicación de un retal."""
        with self._db.get_connection() as conn:
            cur = conn.execute(
                "UPDATE scraps SET shelf_id = ?, storage_area_id = ? WHERE id = ?",
                (shelf.id if shelf else None, shelf.storage_area_id if shelf else None, scrap_id),
            )
            conn.commit()
        return cur.rowcount > 0

    def delete(self, scrap_id: int) -> bool:
        with self._db.get_connection() as conn:
            cur = conn.execute("DELETE FROM scraps WHERE id = ?", (scrap_id,))
            conn.commit()
        return cur.rowcount > 0

    def get_all(self) -> list[Scrap]:
        with self._db.get_connection() as conn:
            rows = conn.execute(self._SELECT_ALL + " ORDER BY sc.created_at DESC").fetchall()
        return [self._row_to_entity(r) for r in rows]

    def get_by_id(self, scrap_id: int) -> Optional[Scrap]:
        with self._db.get_connection() as conn:
            row = conn.execute(
                self._SELECT_ALL + " WHERE sc.id = ?", (scrap_id,)
            ).fetchone()
        return self._row_to_entity(row) if row else None

    def get_by_shelf(self, shelf_id: int) -> list[Scrap]:
        with self._db.get_connection() as conn:
            rows = conn.execute(
                self._SELECT_ALL + " WHERE sc.shelf_id = ? ORDER BY sc.created_at DESC",
                (shelf_id,),
            ).fetchall()
        return [self._row_to_entity(r) for r in rows]

    def get_reusable(self) -> list[Scrap]:
        """Retales reutilizables y no reciclados, del más grande al más pequeño."""
        with self._db.get_connection() as conn:
            rows = conn.execute(
                self._SELECT_ALL
                + " WHERE sc.destination = 'REUTILIZABLE' AND sc.status != 'RECICLADO'"
                + " ORDER BY sc.area_m2 DESC"
            ).fetchall()
        return [self._row_to_entity(r) for r in rows]

    def get_recyclable(self) -> list[Scrap]:
        with self._db.get_connection() as conn:
            rows = conn.execute(
                self._SELECT_ALL
                + " WHERE sc.destination = 'RECICLABLE' ORDER BY sc.created_at DESC"
            ).fetchall()
        return [self._row_to_entity(r) for r in rows]

    def search(
        self,
        min_width_m: Optional[float] = None,
        min_length_m: Optional[float] = None,
        min_area_m2: Optional[float] = None,
        min_thickness_mm: Optional[float] = None,
        shape: Optional[ShapeType] = None,
        only_reusable: bool = True,
    ) -> list[Scrap]:
        """
        Busca retales que cubren una pieza solicitada.

        Los filtros son "mínimo": `min_width_m=0.8` trae los retales de al
        menos 0.8 m de ancho. Como un retal puede girarse 90°, la condición se
        evalúa con `max(ancho, largo) >= pedido_max` y `min(ancho, largo) >= pedido_min`,
        de modo que un retal de 1.0 × 0.4 sirve para pedir 0.5 × 0.9.
        """
        where = []
        params: list = []
        if only_reusable:
            where.append("sc.destination = 'REUTILIZABLE' AND sc.status != 'RECICLADO'")
        if min_area_m2 is not None:
            where.append("sc.area_m2 >= ?")
            params.append(float(min_area_m2))
        if min_thickness_mm is not None:
            where.append("(sc.thickness_mm IS NULL OR sc.thickness_mm >= ?)")
            params.append(float(min_thickness_mm))
        if shape is not None:
            where.append("sc.shape = ?")
            params.append(shape.value)
        if min_width_m is not None and min_length_m is not None:
            # Cabe en alguna rotación: el lado largo cubre el largo pedido y el
            # lado corto cubre el ancho pedido (o al revés).
            where.append(
                "((sc.width_m >= ? AND sc.length_m >= ?)"
                " OR (sc.width_m >= ? AND sc.length_m >= ?))"
            )
            a, b = float(min_width_m), float(min_length_m)
            params.extend([a, b, b, a])
        elif min_width_m is not None:
            where.append("MAX(sc.width_m, sc.length_m) >= ?")
            params.append(float(min_width_m))
        elif min_length_m is not None:
            where.append("MAX(sc.width_m, sc.length_m) >= ?")
            params.append(float(min_length_m))

        sql = self._SELECT_ALL
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY sc.area_m2 DESC"

        with self._db.get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_entity(r) for r in rows]

    def get_statistics(self) -> dict:
        """Totales del inventario para la cabecera de la pestaña."""
        sql = """
        SELECT COUNT(*)                                              AS total,
               COALESCE(SUM(area_m2), 0)                             AS total_area,
               COALESCE(SUM(CASE WHEN destination = 'REUTILIZABLE'
                                 THEN area_m2 ELSE 0 END), 0)        AS reusable_area,
               COALESCE(SUM(CASE WHEN destination = 'RECICLABLE'
                                 THEN area_m2 ELSE 0 END), 0)        AS recyclable_area,
               COALESCE(SUM(CASE WHEN destination = 'REUTILIZABLE'
                                 THEN estimated_value ELSE 0 END), 0) AS total_value,
               COALESCE(SUM(safety_alert), 0)                        AS safety_alerts,
               COALESCE(SUM(CASE WHEN shelf_id IS NULL
                                 AND destination = 'REUTILIZABLE'
                                 THEN 1 ELSE 0 END), 0)              AS unassigned
        FROM scraps
        """
        with self._db.get_connection() as conn:
            row = conn.execute(sql).fetchone()
        return dict(row) if row else {}

    # ── Interno ──────────────────────────────────────────────────────────────

    _SELECT_ALL = """
        SELECT sc.*, sh.name AS shelf_name, sa.name AS area_name
        FROM scraps sc
        LEFT JOIN shelves sh      ON sh.id = sc.shelf_id
        LEFT JOIN storage_areas sa ON sa.id = sc.storage_area_id
    """

    def _params(self, s: Scrap) -> tuple:
        return (
            s.measurement_id,
            s.name,
            float(s.area_m2),
            float(s.width_m),
            float(s.length_m),
            s.thickness_mm,
            s.shape.value,
            s.regularity.value,
            s.shape_confidence,
            s.regularity_score,
            s.vertex_count,
            s.shelf_id,
            s.storage_area_id,
            s.destination.value,
            s.status.value,
            s.sharpness_score,
            int(s.safety_alert),
            s.estimated_value,
            s.cost_per_m2,
            json.dumps(s.reasons, ensure_ascii=False),
            s.silhouette_path,
            s.created_at.isoformat() if s.created_at else _now_iso(),
        )

    @staticmethod
    def _row_to_entity(row: sqlite3.Row) -> Scrap:
        try:
            reasons = json.loads(row["reasons"]) if row["reasons"] else []
            if not isinstance(reasons, list):
                reasons = []
        except (json.JSONDecodeError, TypeError):
            reasons = []
        keys = row.keys()
        return Scrap(
            id=row["id"],
            measurement_id=row["measurement_id"],
            name=row["name"],
            area_m2=row["area_m2"],
            width_m=row["width_m"],
            length_m=row["length_m"],
            thickness_mm=row["thickness_mm"],
            shape=ShapeType(row["shape"]),
            regularity=Regularity(row["regularity"]),
            shape_confidence=row["shape_confidence"],
            regularity_score=row["regularity_score"],
            vertex_count=row["vertex_count"],
            shelf_id=row["shelf_id"],
            storage_area_id=row["storage_area_id"],
            destination=ScrapDestination(row["destination"]),
            status=ScrapStatus(row["status"]),
            sharpness_score=row["sharpness_score"],
            safety_alert=bool(row["safety_alert"]),
            estimated_value=row["estimated_value"],
            cost_per_m2=row["cost_per_m2"],
            reasons=reasons,
            silhouette_path=row["silhouette_path"],
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            shelf_name=row["shelf_name"] if "shelf_name" in keys else None,
            storage_area_name=row["area_name"] if "area_name" in keys else None,
        )
