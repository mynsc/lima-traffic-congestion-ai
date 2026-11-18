import logging
import sqlite3
from pathlib import Path

from config.settings import DB_PATH

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS calle (
    id_calle INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    roi_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ciclo_semaforo (
    id_ciclo INTEGER PRIMARY KEY AUTOINCREMENT,
    id_calle INTEGER NOT NULL REFERENCES calle (id_calle),
    fase_inicio TEXT NOT NULL,
    segundos_verde_asignados INTEGER NOT NULL,
    modo TEXT NOT NULL,
    tipo_evento TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS registro_vehiculos (
    id_registro INTEGER PRIMARY KEY AUTOINCREMENT,
    id_ciclo INTEGER NOT NULL REFERENCES ciclo_semaforo (id_ciclo),
    cantidad_autos INTEGER NOT NULL,
    cantidad_buses INTEGER NOT NULL,
    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS metricas_espera (
    id_metrica INTEGER PRIMARY KEY AUTOINCREMENT,
    id_ciclo INTEGER NOT NULL REFERENCES ciclo_semaforo (id_ciclo),
    segundos_rojo INTEGER NOT NULL,
    espera_promedio_seg REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ciclo_calle ON ciclo_semaforo (id_calle);
CREATE INDEX IF NOT EXISTS idx_registro_ciclo ON registro_vehiculos (id_ciclo);
CREATE INDEX IF NOT EXISTS idx_metrica_ciclo ON metricas_espera (id_ciclo);
"""


def crear_tablas(conn: sqlite3.Connection) -> None:
    with conn:
        conn.executescript(SCHEMA)


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    crear_tablas(conn)
    return conn