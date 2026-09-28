"""
Pruebas de la migración del esquema SQLite v1 → v2.

El requisito es explícito: **no se deben perder mediciones históricas**.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest

from core.entities import MeasurementCategory
from data.database import SCHEMA_VERSION, DatabaseManager
from data.repositories import MeasurementRepository

SCHEMA_V1_MEASUREMENTS = """
CREATE TABLE measurements (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    name             TEXT,
    area_pixels      REAL    NOT NULL,
    area_m2          REAL    NOT NULL,
    category         TEXT    NOT NULL,
    factor_k_used    REAL    NOT NULL,
    distance_cm      REAL    NOT NULL,
    timestamp        TEXT    NOT NULL,
    notes            TEXT,
    silhouette_path  TEXT,
    perimeter_pixels REAL,
    circularity      REAL,
    confidence       REAL,
    is_valid         INTEGER NOT NULL DEFAULT 1
);
"""

HISTORICOS = [
    ("Lámina sala 3",  48000.0, 0.0623, "A", 80.0, "2026-03-14T10:30:00", "histórico 1", 1),
    ("Panel taller",  120000.0, 1.4,    "B", 50.0, "2026-03-15T11:00:00", "histórico 2", 1),
    ("Retal inválido",   3000.0, 0.004,  "A", 45.0, "2026-03-16T09:15:00", "descartado", 0),
]


@pytest.fixture
def v1_database(tmp_path):
    """Crea una base en esquema v1 con datos históricos reales."""
    path = str(tmp_path / "measurements.db")
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_V1_MEASUREMENTS)
    conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO meta VALUES ('schema_version', '1')")
    conn.executemany(
        """INSERT INTO measurements
           (name, area_pixels, area_m2, category, factor_k_used, distance_cm,
            timestamp, notes, is_valid)
           VALUES (?, ?, ?, ?, 1.3e-6, ?, ?, ?, ?)""",
        HISTORICOS,
    )
    conn.commit()
    conn.close()
    return path


class TestMigration:
    def test_crea_las_tablas_nuevas(self, v1_database):
        DatabaseManager(v1_database).initialize()
        conn = sqlite3.connect(v1_database)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        assert {"storage_areas", "shelves", "scraps"} <= tables

    def test_añade_la_columna_scrap_id(self, v1_database):
        DatabaseManager(v1_database).initialize()
        conn = sqlite3.connect(v1_database)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(measurements)")]
        conn.close()
        assert "scrap_id" in cols

    def test_actualiza_la_version_del_esquema(self, v1_database):
        DatabaseManager(v1_database).initialize()
        conn = sqlite3.connect(v1_database)
        ver = conn.execute(
            "SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
        conn.close()
        assert ver == str(SCHEMA_VERSION) == "2"

    def test_es_idempotente(self, v1_database):
        """Ejecutarla dos veces no debe romper nada (se hace al abrir la app)."""
        db = DatabaseManager(v1_database)
        db.initialize()
        db.initialize()
        db.initialize()
        repo = MeasurementRepository(db)
        assert len(repo.get_all()) == len(HISTORICOS)


class TestNoDataLoss:
    def test_conserva_todas_las_filas(self, v1_database):
        before = MeasurementRepository(DatabaseManager(v1_database))  # sin migrar aún
        with sqlite3.connect(v1_database) as c:
            count_before = c.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]

        DatabaseManager(v1_database).initialize()

        with sqlite3.connect(v1_database) as c:
            count_after = c.execute("SELECT COUNT(*) FROM measurements").fetchone()[0]
        assert count_before == count_after == len(HISTORICOS)
        _ = before

    def test_conserva_los_valores(self, v1_database):
        with sqlite3.connect(v1_database) as c:
            before = c.execute(
                "SELECT id, name, area_m2, category, timestamp, notes, is_valid "
                "FROM measurements ORDER BY id").fetchall()
        DatabaseManager(v1_database).initialize()
        with sqlite3.connect(v1_database) as c:
            after = c.execute(
                "SELECT id, name, area_m2, category, timestamp, notes, is_valid "
                "FROM measurements ORDER BY id").fetchall()
        assert before == after

    def test_las_historicas_quedan_sin_retal(self, v1_database):
        DatabaseManager(v1_database).initialize()
        repo = MeasurementRepository(DatabaseManager(v1_database))
        assert all(m.scrap_id is None for m in repo.get_all())

    def test_el_repositorio_sigue_leyendo(self, v1_database):
        DatabaseManager(v1_database).initialize()
        repo = MeasurementRepository(DatabaseManager(v1_database))
        items = repo.get_all()
        assert len(items) == len(HISTORICOS)
        m = next(x for x in items if x.name == "Panel taller")
        assert m.area_m2 == pytest.approx(1.4)
        assert m.category == MeasurementCategory.B
        assert m.notes == "histórico 2"
        assert m.is_valid is True

    def test_las_estadisticas_no_cambian(self, v1_database):
        """El filtro is_valid=1 debe seguir dando 2, no 3."""
        with sqlite3.connect(v1_database) as c:
            c.row_factory = sqlite3.Row
            esperado = dict(c.execute(
                "SELECT COUNT(*) AS total, SUM(area_m2) AS s FROM measurements "
                "WHERE is_valid = 1").fetchone())
        DatabaseManager(v1_database).initialize()
        stats = MeasurementRepository(DatabaseManager(v1_database)).get_statistics()
        assert stats["total"] == esperado["total"] == 2
        assert stats["total_area"] == pytest.approx(esperado["s"])

    def test_el_csv_sigue_funcionando(self, v1_database):
        DatabaseManager(v1_database).initialize()
        csv = MeasurementRepository(DatabaseManager(v1_database)).export_csv()
        assert csv.count("\n") == len(HISTORICOS)
        assert "Panel taller" in csv

    def test_borrado_sigue_funcionando(self, v1_database):
        db = DatabaseManager(v1_database)
        db.initialize()
        repo = MeasurementRepository(db)
        victim = next(m for m in repo.get_all() if m.name == "Retal inválido")
        assert repo.delete(victim.id) is True
        assert len(repo.get_all()) == len(HISTORICOS) - 1


class TestRoundTrip:
    def test_guarda_y_recupera_un_retal_enlazado(self, repos, db_manager):
        """Una medición nueva puede enlazar con su retal (`scrap_id`)."""
        from conftest import make_scrap
        from core.entities import ScrapDestination, ShapeType
        _, _, scrap_repo = repos

        scrap = make_scrap(ShapeType.RECTANGULO, 2.0, 1.2, thickness_mm=3.0)
        scrap_id = scrap_repo.save(scrap)

        repo = MeasurementRepository(db_manager)
        m_id = repo.save(_medicion(scrap_id=scrap_id))
        recuperada = repo.get_by_id(m_id)
        assert recuperada.scrap_id == scrap_id

    def test_medicion_sin_retal_sigue_siendo_valida(self, db_manager):
        repo = MeasurementRepository(db_manager)
        m_id = repo.save(_medicion(scrap_id=None))
        assert repo.get_by_id(m_id).scrap_id is None

    def test_borrar_el_retal_no_borra_la_medicion(self, repos, db_manager):
        """`scrap_id` es una referencia lógica, no una FK dura: el historial manda."""
        from conftest import make_scrap
        from core.entities import ShapeType
        _, _, scrap_repo = repos

        scrap = make_scrap(ShapeType.RECTANGULO, 1.0, 0.8)
        scrap_id = scrap_repo.save(scrap)
        repo = MeasurementRepository(db_manager)
        m_id = repo.save(_medicion(scrap_id=scrap_id))

        scrap_repo.delete(scrap_id)
        assert repo.get_by_id(m_id) is not None


def _medicion(scrap_id=None):
    from core.entities import Measurement
    return Measurement(
        name="Prueba", area_pixels=48000.0, area_m2=1.4,
        category=MeasurementCategory.B, factor_k_used=1.3e-6,
        distance_cm=50.0, timestamp=datetime(2026, 9, 26, 10, 0, 0),
        notes=None, scrap_id=scrap_id,
    )
