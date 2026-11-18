import json
import logging
import sqlite3
from datetime import datetime
from typing import Optional

import pandas as pd

from config.settings import ROIS

logger = logging.getLogger(__name__)


def insertar_calles_iniciales(
    conn: sqlite3.Connection, rois: Optional[dict] = None
) -> None:
    rois = ROIS if rois is None else rois
    filas = [(nombre, json.dumps(poligono)) for nombre, poligono in rois.items()]
    try:
        with conn:
            conn.executemany(
                "INSERT OR IGNORE INTO calle (nombre, roi_json) VALUES (?, ?)",
                filas,
            )
    except sqlite3.Error:
        logger.exception("Error insertando calles iniciales")


def guardar_ciclo_completo(
    conn: sqlite3.Connection,
    nombre_calle: str,
    fase_inicio: str,
    segundos_verde: int,
    segundos_rojo: int,
    modo: str,
    tipo_evento: str,
    autos: int,
    buses: int,
    timestamp: Optional[str] = None,
) -> bool:
    timestamp = timestamp or datetime.now().isoformat(timespec="seconds")
    espera_promedio = segundos_rojo / 2
    try:
        with conn:
            fila = conn.execute(
                "SELECT id_calle FROM calle WHERE nombre = ?", (nombre_calle,)
            ).fetchone()
            if fila is None:
                raise ValueError(f"Calle no registrada: {nombre_calle}")
            cursor = conn.execute(
                "INSERT INTO ciclo_semaforo (id_calle, fase_inicio, "
                "segundos_verde_asignados, modo, tipo_evento) "
                "VALUES (?, ?, ?, ?, ?)",
                (fila["id_calle"], fase_inicio, segundos_verde, modo, tipo_evento),
            )
            id_ciclo = cursor.lastrowid
            conn.execute(
                "INSERT INTO registro_vehiculos (id_ciclo, cantidad_autos, "
                "cantidad_buses, timestamp) VALUES (?, ?, ?, ?)",
                (id_ciclo, autos, buses, timestamp),
            )
            conn.execute(
                "INSERT INTO metricas_espera (id_ciclo, segundos_rojo, "
                "espera_promedio_seg) VALUES (?, ?, ?)",
                (id_ciclo, segundos_rojo, espera_promedio),
            )
        return True
    except (sqlite3.Error, ValueError):
        logger.exception("Error guardando ciclo de %s", nombre_calle)
        return False


def _consultar(
    conn: sqlite3.Connection, sql: str, params: tuple = ()
) -> pd.DataFrame:
    try:
        return pd.read_sql_query(sql, conn, params=params)
    except (sqlite3.Error, pd.errors.DatabaseError):
        logger.exception("Error en consulta de dashboard")
        return pd.DataFrame()


def obtener_resumen_calles(conn: sqlite3.Connection) -> pd.DataFrame:
    sql = """
        SELECT c.nombre AS calle,
               COUNT(cs.id_ciclo) AS ciclos,
               ROUND(AVG(cs.segundos_verde_asignados), 1) AS verde_promedio,
               ROUND(AVG(rv.cantidad_autos), 1) AS autos_promedio,
               ROUND(AVG(rv.cantidad_buses), 1) AS buses_promedio,
               ROUND(AVG(me.espera_promedio_seg), 1) AS espera_promedio
        FROM calle c
        LEFT JOIN ciclo_semaforo cs ON cs.id_calle = c.id_calle
        LEFT JOIN registro_vehiculos rv ON rv.id_ciclo = cs.id_ciclo
        LEFT JOIN metricas_espera me ON me.id_ciclo = cs.id_ciclo
        GROUP BY c.id_calle
        ORDER BY c.nombre
    """
    return _consultar(conn, sql)


def obtener_ultimos_ciclos(
    conn: sqlite3.Connection, limite: int = 50
) -> pd.DataFrame:
    sql = """
        SELECT cs.id_ciclo, c.nombre AS calle, cs.fase_inicio,
               cs.segundos_verde_asignados, cs.modo, cs.tipo_evento,
               rv.cantidad_autos, rv.cantidad_buses,
               me.segundos_rojo, me.espera_promedio_seg
        FROM ciclo_semaforo cs
        JOIN calle c ON c.id_calle = cs.id_calle
        JOIN registro_vehiculos rv ON rv.id_ciclo = cs.id_ciclo
        JOIN metricas_espera me ON me.id_ciclo = cs.id_ciclo
        ORDER BY cs.id_ciclo DESC
        LIMIT ?
    """
    return _consultar(conn, sql, (limite,))


def obtener_serie_vehiculos(
    conn: sqlite3.Connection, limite: int = 200
) -> pd.DataFrame:
    sql = """
        SELECT rv.timestamp, c.nombre AS calle,
               rv.cantidad_autos, rv.cantidad_buses
        FROM registro_vehiculos rv
        JOIN ciclo_semaforo cs ON cs.id_ciclo = rv.id_ciclo
        JOIN calle c ON c.id_calle = cs.id_calle
        ORDER BY rv.id_registro DESC
        LIMIT ?
    """
    df = _consultar(conn, sql, (limite,))
    return df.iloc[::-1].reset_index(drop=True)


def obtener_comparativa_modos(conn: sqlite3.Connection) -> pd.DataFrame:
    sql = """
        SELECT cs.modo,
               COUNT(*) AS ciclos,
               ROUND(AVG(cs.segundos_verde_asignados), 1) AS verde_promedio,
               ROUND(AVG(me.espera_promedio_seg), 1) AS espera_promedio
        FROM ciclo_semaforo cs
        JOIN metricas_espera me ON me.id_ciclo = cs.id_ciclo
        GROUP BY cs.modo
    """
    return _consultar(conn, sql)


def obtener_eventos_emergencia(conn: sqlite3.Connection) -> pd.DataFrame:
    sql = """
        SELECT c.nombre AS calle, cs.fase_inicio, cs.segundos_verde_asignados
        FROM ciclo_semaforo cs
        JOIN calle c ON c.id_calle = cs.id_calle
        WHERE cs.tipo_evento = 'EMERGENCY_OVERRIDE'
        ORDER BY cs.id_ciclo DESC
    """
    return _consultar(conn, sql)