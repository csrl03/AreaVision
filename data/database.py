"""
Gestión de la base de datos SQLite.

Toda la inicialización y acceso al schema pasa por este módulo.
Las queries usan placeholders '?' para prevenir inyección SQL.
"""
import sqlite3
import logging
from config import DB_PATH

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

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

_CREATE_META = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


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
        """Crea las tablas si no existen y registra la versión del schema."""
        with self.get_connection() as conn:
            conn.execute(_CREATE_MEASUREMENTS)
            conn.execute(_CREATE_META)
            conn.execute(
                "INSERT OR IGNORE INTO meta (key, value) VALUES (?, ?)",
                ("schema_version", str(SCHEMA_VERSION)),
            )
            conn.commit()
        logger.info("Base de datos lista: %s", self._db_path)
