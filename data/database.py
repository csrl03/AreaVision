"""
Gestión de la base de datos SQLite.

Toda la inicialización y acceso al schema pasa por este módulo.
Las queries usan placeholders '?' para prevenir inyección SQL.
"""
import sqlite3
import logging
from config import DB_PATH

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2

_CREATE_MEASUREMENTS = """
CREATE TABLE IF NOT EXISTS measurements (
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

# ─── Almacén de retales (v2) ──────────────────────────────────────────────────
# Relación: storage_areas 1─N shelves 1─N scraps
#   measurements.scrap_id es NULLABLE para no tocar el historial existente.

_CREATE_STORAGE_AREAS = """
CREATE TABLE IF NOT EXISTS storage_areas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT,
    created_at  TEXT NOT NULL
);
"""

_CREATE_SHELVES = """
CREATE TABLE IF NOT EXISTS shelves (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    storage_area_id   INTEGER NOT NULL REFERENCES storage_areas(id) ON DELETE CASCADE,
    name              TEXT    NOT NULL,
    width_m           REAL    NOT NULL,
    length_m          REAL    NOT NULL,
    accepts_regular   INTEGER NOT NULL DEFAULT 1,
    accepts_irregular INTEGER NOT NULL DEFAULT 1,
    min_width_m       REAL,
    max_width_m       REAL,
    min_length_m      REAL,
    max_length_m      REAL,
    min_area_m2       REAL,
    max_area_m2       REAL,
    min_thickness_mm  REAL,
    max_thickness_mm  REAL,
    created_at        TEXT    NOT NULL
);
"""

_CREATE_SCRAPS = """
CREATE TABLE IF NOT EXISTS scraps (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    measurement_id    INTEGER,
    name              TEXT,
    area_m2           REAL    NOT NULL,
    width_m           REAL    NOT NULL,
    length_m          REAL    NOT NULL,
    thickness_mm      REAL,
    shape             TEXT    NOT NULL,
    regularity        TEXT    NOT NULL,
    shape_confidence  REAL,
    regularity_score  REAL,
    vertex_count      INTEGER,
    shelf_id          INTEGER REFERENCES shelves(id) ON DELETE SET NULL,
    storage_area_id   INTEGER,
    destination       TEXT    NOT NULL,
    status            TEXT    NOT NULL DEFAULT 'DISPONIBLE',
    sharpness_score   REAL,
    safety_alert      INTEGER NOT NULL DEFAULT 0,
    estimated_value   REAL,
    cost_per_m2       REAL,
    reasons           TEXT,
    silhouette_path   TEXT,
    created_at        TEXT    NOT NULL
);
"""

# Índices de consulta: el inventario filtra por destino/estado/ubicación, y la
# asignación busca porshelf_id constantemente.
_CREATE_INDICES = (
    "CREATE INDEX IF NOT EXISTS idx_shelves_area ON shelves(storage_area_id)",
    "CREATE INDEX IF NOT EXISTS idx_scraps_shelf ON scraps(shelf_id)",
    "CREATE INDEX IF NOT EXISTS idx_scraps_destination ON scraps(destination, status)",
    "CREATE INDEX IF NOT EXISTS idx_measurements_scrap ON measurements(scrap_id)",
)

_CREATE_META = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# Columna añadida en v2. Nullable a propósito: las mediciones históricas no
# tienen retal asociado y deben seguir siendo legibles tal cual.
_MEASUREMENTS_V2_COLUMNS = (
    ("scrap_id", "INTEGER"),
)


def _migrate_to_v2(conn: sqlite3.Connection) -> None:
    """
    Aplica la migración v1 → v2.

    Es idempotente y no destructiva:
    - `CREATE TABLE IF NOT EXISTS` no falla si la tabla ya existe.
    - `ALTER TABLE ADD COLUMN` se envuelve en try/except porque SQLite no tiene
      `ADD COLUMN IF NOT EXISTS`; reintentar sobre una base ya migrada lanza
      "duplicate column name", que es exactamente el caso que queremos ignorar.
    - No se reescribe ni se borra ninguna fila de `measurements`.
    """
    for ddl in (_CREATE_STORAGE_AREAS, _CREATE_SHELVES, _CREATE_SCRAPS):
        conn.execute(ddl)
    for col_name, col_type in _MEASUREMENTS_V2_COLUMNS:
        try:
            conn.execute(f"ALTER TABLE measurements ADD COLUMN {col_name} {col_type}")
            logger.info("Migración v2: columna measurements.%s añadida", col_name)
        except sqlite3.OperationalError as exc:
            if "duplicate column name" in str(exc).lower():
                logger.debug("La columna measurements.%s ya existía", col_name)
            else:
                raise
    for ddl in _CREATE_INDICES:
        conn.execute(ddl)


class DatabaseManager:
    """Gestiona la conexión y el schema de la base de datos SQLite."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self._db_path = db_path

    def get_connection(self) -> sqlite3.Connection:
        """
        Abre una conexión con row_factory y pragmas de seguridad/rendimiento.
        Usar en bloque 'with' para auto-commit/rollback.
        """
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")   # Write-Ahead Logging: mejor concurrencia
        return conn

    def initialize(self) -> None:
        """
        Crea las tablas si no existen, aplica las migraciones pendientes
        y registra la versión del schema.
        """
        with self.get_connection() as conn:
            conn.execute(_CREATE_MEASUREMENTS)
            conn.execute(_CREATE_META)
            _migrate_to_v2(conn)
            conn.execute(
                "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )
            conn.commit()
        logger.info("Base de datos lista (schema v%d): %s", SCHEMA_VERSION, self._db_path)
