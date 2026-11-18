import logging
import time

import cv2

from config.settings import VIDEO_PATH
from src.controller.traffic_logic import EstadoSemaforo, TrafficController
from src.database.connection import get_connection
from src.database.repository import (
    guardar_ciclo_completo,
    insertar_calles_iniciales,
)
from src.simulation.renderer import Renderer
from src.vision.detector import VehicleDetector
from src.vision.tracker import ROISnapshotTracker
from src.vision.video_stream import VideoStream

VENTANA = "Smart Traffic Lima"
FRAME_SIZE = (1280, 720)
MAX_DT = 1.0
TECLAS_SALIDA = {ord("q"), ord("Q"), 27}
TECLAS_EMERGENCIA = {ord("e"), ord("E")}
TECLAS_MODO = {ord("m"), ord("M")}
TECLAS_PAUSA = {ord("p"), ord("P")}


def registrar_ciclo(conn, tracker: ROISnapshotTracker, estado: EstadoSemaforo) -> None:
    info = estado.ciclo_completado_info
    if info is None:
        return
    guardar_ciclo_completo(
        conn,
        info.calle,
        info.fase_inicio,
        info.segundos_verde,
        info.segundos_rojo,
        info.modo,
        info.tipo_evento,
        info.autos,
        info.buses,
    )
    tracker.reiniciar(info.calle)


def manejar_tecla(
    tecla: int,
    controller: TrafficController,
    stream: VideoStream,
    pausado: bool,
) -> tuple[bool, bool]:
    if tecla in TECLAS_SALIDA:
        return True, pausado
    if tecla in TECLAS_EMERGENCIA:
        controller.emergencia()
    elif tecla in TECLAS_MODO:
        controller.toggle_modo()
    elif tecla in TECLAS_PAUSA:
        pausado = not pausado
        if pausado:
            stream.pause()
        else:
            stream.resume()
    return False, pausado


def suavizar_fps(fps: float, dt: float) -> float:
    instantaneo = 1.0 / max(dt, 1e-6)
    return instantaneo if fps == 0.0 else 0.9 * fps + 0.1 * instantaneo


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    conn = get_connection()
    insertar_calles_iniciales(conn)
    stream = VideoStream(VIDEO_PATH, loop=True)
    detector = VehicleDetector()
    tracker = ROISnapshotTracker()
    controller = TrafficController()
    renderer = Renderer()

    estado = controller.tick(0.0, tracker.maximos())
    detecciones = []
    pausado = False
    fps = 0.0
    previo = time.monotonic()

    try:
        while True:
            ok, frame = stream.read()
            if not ok:
                break
            frame = cv2.resize(frame, FRAME_SIZE)
            ahora = time.monotonic()
            dt_real = ahora - previo
            previo = ahora

            if not pausado:
                detecciones = detector.detect(frame)
                if detector.inferencia_reciente:
                    tracker.update(detecciones, ahora)
                estado = controller.tick(min(dt_real, MAX_DT), tracker.maximos())
                registrar_ciclo(conn, tracker, estado)
                fps = suavizar_fps(fps, dt_real)

            renderer.dibujar(
                frame,
                detecciones,
                estado,
                tracker.conteo_actual(),
                tracker.maximos(),
                fps,
            )
            cv2.imshow(VENTANA, frame)
            tecla = cv2.waitKey(1) & 0xFF
            salir, pausado = manejar_tecla(tecla, controller, stream, pausado)
            if salir:
                break
    finally:
        stream.release()
        cv2.destroyAllWindows()
        conn.close()


if __name__ == "__main__":
    main()