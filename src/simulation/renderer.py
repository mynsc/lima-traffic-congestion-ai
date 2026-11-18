from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

import cv2
import numpy as np

from config.settings import ROIS

if TYPE_CHECKING:
    from src.controller.traffic_logic import EstadoSemaforo
    from src.vision.detector import Detection

FUENTE = cv2.FONT_HERSHEY_SIMPLEX
COLORES_ROI = {"Calle_A": (0, 165, 255), "Calle_B": (255, 0, 255)}
COLOR_ROI_DEFECTO = (200, 200, 200)
COLORES_CLASE = {"car": (0, 200, 0), "bus": (255, 100, 0)}
COLORES_LUZ = {
    "ROJO": (0, 0, 255),
    "AMARILLO": (0, 255, 255),
    "VERDE": (0, 220, 0),
}
LUZ_APAGADA = (50, 50, 50)
ALTO_BANNER = 50


def _texto(
    frame: np.ndarray,
    texto: str,
    pos: tuple[int, int],
    escala: float = 0.6,
    color: tuple[int, int, int] = (255, 255, 255),
    grosor: int = 2,
) -> None:
    cv2.putText(frame, texto, pos, FUENTE, escala, (0, 0, 0), grosor + 2, cv2.LINE_AA)
    cv2.putText(frame, texto, pos, FUENTE, escala, color, grosor, cv2.LINE_AA)


class Renderer:
    def __init__(self, rois: Optional[dict] = None, alpha: float = 0.25) -> None:
        self.rois = ROIS if rois is None else rois
        self.alpha = alpha
        self._poligonos = {
            nombre: np.array(puntos, dtype=np.int32)
            for nombre, puntos in self.rois.items()
        }

    def dibujar(
        self,
        frame: np.ndarray,
        detecciones: list[Detection],
        estado: EstadoSemaforo,
        actual: dict,
        maximos: dict,
        fps: float,
    ) -> np.ndarray:
        self._dibujar_rois(frame)
        self._dibujar_detecciones(frame, detecciones)
        self._dibujar_semaforos(frame, estado)
        self._dibujar_panel(frame, estado, actual, maximos, fps)
        if estado.es_emergencia:
            self._dibujar_banner(frame)
        return frame

    def _dibujar_rois(self, frame: np.ndarray) -> None:
        overlay = frame.copy()
        for nombre, poligono in self._poligonos.items():
            color = COLORES_ROI.get(nombre, COLOR_ROI_DEFECTO)
            cv2.fillPoly(overlay, [poligono], color)
        cv2.addWeighted(overlay, self.alpha, frame, 1 - self.alpha, 0, dst=frame)
        for nombre, poligono in self._poligonos.items():
            color = COLORES_ROI.get(nombre, COLOR_ROI_DEFECTO)
            cv2.polylines(frame, [poligono], True, color, 2)
            x, y = poligono[0]
            _texto(frame, nombre, (int(x) + 8, int(y) + 24), 0.7, color)

    @staticmethod
    def _dibujar_detecciones(frame: np.ndarray, detecciones: list[Detection]) -> None:
        for det in detecciones:
            x1, y1, x2, y2 = det.bbox
            color = COLORES_CLASE.get(det.clase, (255, 255, 255))
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.circle(frame, ((x1 + x2) // 2, y2), 4, color, -1)
            ident = "-" if det.track_id is None else det.track_id
            etiqueta = f"{det.clase} #{ident} {det.conf:.2f}"
            _texto(frame, etiqueta, (x1, max(y1 - 6, 14)), 0.45, color, 1)

    @staticmethod
    def _dibujar_semaforos(frame: np.ndarray, estado: EstadoSemaforo) -> None:
        ancho = frame.shape[1]
        luces = {"A": estado.luz_A, "B": estado.luz_B}
        segundos = math.ceil(estado.segundos_restantes)
        for i, nombre in enumerate(("A", "B")):
            x0 = ancho - 190 + i * 90
            y0 = ALTO_BANNER + 20
            cv2.rectangle(frame, (x0, y0), (x0 + 70, y0 + 190), (30, 30, 30), -1)
            cv2.rectangle(frame, (x0, y0), (x0 + 70, y0 + 190), (255, 255, 255), 1)
            for j, luz in enumerate(("ROJO", "AMARILLO", "VERDE")):
                centro = (x0 + 35, y0 + 35 + j * 60)
                encendida = luces[nombre] == luz
                color = COLORES_LUZ[luz] if encendida else LUZ_APAGADA
                cv2.circle(frame, centro, 20, color, -1)
            _texto(frame, f"Calle {nombre}", (x0 - 2, y0 + 215), 0.55)
            cuenta = f"{segundos}s" if luces[nombre] != "ROJO" else "--"
            _texto(frame, cuenta, (x0 + 5, y0 + 250), 0.9, (0, 255, 255))

    @staticmethod
    def _dibujar_panel(
        frame: np.ndarray,
        estado: EstadoSemaforo,
        actual: dict,
        maximos: dict,
        fps: float,
    ) -> None:
        lineas = [
            f"Modo: {estado.modo}",
            f"Fase: {estado.fase}",
            f"FPS: {fps:.1f}",
        ]
        for calle in ("Calle_A", "Calle_B"):
            act = actual.get(calle, {})
            mx = maximos.get(calle, {})
            lineas.append(
                f"{calle}: {act.get('autos', 0)} autos, "
                f"{act.get('buses', 0)} buses "
                f"(max {mx.get('autos', 0)}/{mx.get('buses', 0)})"
            )
        for i, linea in enumerate(lineas):
            _texto(frame, linea, (12, ALTO_BANNER + 30 + i * 28), 0.65)

    @staticmethod
    def _dibujar_banner(frame: np.ndarray) -> None:
        ancho = frame.shape[1]
        cv2.rectangle(frame, (0, 0), (ancho, ALTO_BANNER), (0, 0, 255), -1)
        (tw, th), _ = cv2.getTextSize("EMERGENCIA", FUENTE, 1.2, 3)
        pos = ((ancho - tw) // 2, (ALTO_BANNER + th) // 2)
        cv2.putText(
            frame, "EMERGENCIA", pos, FUENTE, 1.2, (255, 255, 255), 3, cv2.LINE_AA
        )