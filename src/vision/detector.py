import logging
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
from ultralytics import YOLO

from config.settings import CONF_THRESHOLD, FRAME_SKIP, IMGSZ, MODEL_PATH, ROIS

logger = logging.getLogger(__name__)

CLASES = {2: "car", 5: "bus"}


@dataclass(frozen=True)
class Detection:
    bbox: tuple[int, int, int, int]
    clase: str
    conf: float
    track_id: Optional[int]
    calle: str


class VehicleDetector:
    def __init__(
        self,
        model_path: str = MODEL_PATH,
        rois: Optional[dict] = None,
        frame_skip: int = FRAME_SKIP,
    ) -> None:
        self.model = YOLO(model_path)
        self.rois = ROIS if rois is None else rois
        self._poligonos = {
            nombre: np.array(puntos, dtype=np.int32).reshape(-1, 1, 2)
            for nombre, puntos in self.rois.items()
        }
        self.frame_skip = max(1, frame_skip)
        self.inferencia_reciente = False
        self._contador = 0
        self._ultimas: list[Detection] = []

    def detect(self, frame: np.ndarray) -> list[Detection]:
        toca_inferir = self._contador % self.frame_skip == 0
        self._contador += 1
        self.inferencia_reciente = toca_inferir
        if toca_inferir:
            self._ultimas = self._inferir(frame)
        return self._ultimas

    def _inferir(self, frame: np.ndarray) -> list[Detection]:
        resultados = self.model.track(
            frame,
            persist=True,
            tracker="bytetrack.yaml",
            imgsz=IMGSZ,
            classes=list(CLASES),
            conf=CONF_THRESHOLD,
            verbose=False,
        )
        cajas = resultados[0].boxes
        if cajas is None or len(cajas) == 0:
            return []
        xyxy = cajas.xyxy.cpu().numpy()
        confs = cajas.conf.cpu().numpy()
        clases = cajas.cls.cpu().numpy().astype(int)
        if cajas.id is not None:
            ids = cajas.id.cpu().numpy().astype(int).tolist()
        else:
            ids = [None] * len(xyxy)

        detecciones = []
        for caja, conf, clase, track_id in zip(xyxy, confs, clases, ids):
            if conf < CONF_THRESHOLD or int(clase) not in CLASES:
                continue
            x1, y1, x2, y2 = (int(v) for v in caja)
            calle = self._calle_de((x1 + x2) / 2.0, float(y2))
            if calle is None:
                continue
            detecciones.append(
                Detection(
                    bbox=(x1, y1, x2, y2),
                    clase=CLASES[int(clase)],
                    conf=float(conf),
                    track_id=track_id,
                    calle=calle,
                )
            )
        return detecciones

    def _calle_de(self, x: float, y: float) -> Optional[str]:
        for nombre, poligono in self._poligonos.items():
            if cv2.pointPolygonTest(poligono, (x, y), False) >= 0:
                return nombre
        return None