import argparse
import math
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import AMARILLO, DB_PATH, ROIS, VERDE_EMERGENCIA, VERDE_FIJO  # noqa: E402
from src.controller.traffic_logic import (  # noqa: E402
    EMERGENCY_OVERRIDE,
    MODO_ADAPTATIVO,
    MODO_FIJO,
    TIPO_NORMAL,
    calcular_verde,
)
from src.database.connection import get_connection  # noqa: E402
from src.database.repository import (  # noqa: E402
    guardar_ciclo_completo,
    insertar_calles_iniciales,
)

BLOQUE_MODO = timedelta(minutes=30)
PROB_EMERGENCIA = 0.03


def demanda(momento: datetime, factor: float) -> float:
    hora = momento.hour + momento.minute / 60
    return factor * (8 + 10 * abs(math.sin(math.pi * hora / 12)))


def modo_en(inicio: datetime, momento: datetime) -> str:
    bloque = (momento - inicio) // BLOQUE_MODO
    return MODO_ADAPTATIVO if bloque % 2 == 0 else MODO_FIJO


def limpiar(conn) -> None:
    with conn:
        conn.execute("DELETE FROM metricas_espera")
        conn.execute("DELETE FROM registro_vehiculos")
        conn.execute("DELETE FROM ciclo_semaforo")


def generar(conn, horas: float, semilla: int) -> int:
    rng = random.Random(semilla)
    calles = sorted(ROIS)[:2]
    factores = {calles[0]: 1.0, calles[1]: 0.8}
    ahora = datetime.now().replace(microsecond=0)
    inicio = ahora - timedelta(hours=horas)
    cursor = inicio
    guardados = 0

    while cursor < ahora:
        modo = modo_en(inicio, cursor)
        conteos = {}
        verdes = {}
        tipos = {calle: TIPO_NORMAL for calle in calles}
        for calle in calles:
            autos = max(0, int(rng.gauss(demanda(cursor, factores[calle]), 4)))
            buses = rng.randint(0, 3)
            conteos[calle] = (autos, buses)
            verdes[calle] = VERDE_FIJO if modo == MODO_FIJO else calcular_verde(
                autos, buses
            )
        if rng.random() < PROB_EMERGENCIA:
            prioritaria = rng.choice(calles)
            verdes[prioritaria] = VERDE_EMERGENCIA
            tipos[prioritaria] = EMERGENCY_OVERRIDE

        for calle, otra in zip(calles, reversed(calles)):
            verde = verdes[calle]
            rojo = verdes[otra] + AMARILLO
            fin_verde = cursor + timedelta(seconds=verde)
            autos, buses = conteos[calle]
            ok = guardar_ciclo_completo(
                conn,
                calle,
                cursor.isoformat(timespec="seconds"),
                verde,
                rojo,
                modo,
                tipos[calle],
                autos,
                buses,
                timestamp=fin_verde.isoformat(timespec="seconds"),
            )
            guardados += int(ok)
            cursor = fin_verde + timedelta(seconds=AMARILLO)
    return guardados


def main() -> None:
    parser = argparse.ArgumentParser(description="Datos sintéticos de demo")
    parser.add_argument("--db", default=DB_PATH)
    parser.add_argument("--horas", type=float, default=6.0)
    parser.add_argument("--semilla", type=int, default=42)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    conn = get_connection(args.db)
    try:
        insertar_calles_iniciales(conn)
        if args.reset:
            limpiar(conn)
        total = generar(conn, args.horas, args.semilla)
    finally:
        conn.close()
    print(f"Ciclos insertados: {total} en {args.db}")


if __name__ == "__main__":
    main()