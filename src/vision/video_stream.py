import logging
import queue
import threading
import time
from pathlib import Path
from typing import Iterator, Optional, Union

import cv2
import numpy as np

logger = logging.getLogger(__name__)

PREFIJOS_STREAM = ("rtsp://", "rtmp://", "http://", "https://")
FPS_POR_DEFECTO = 30.0
REINTENTOS_STREAM = 5


class VideoStream:
    def __init__(self, source: Union[str, Path], loop: bool = True) -> None:
        self.source = str(source)
        self.loop = loop
        self.es_stream = self.source.lower().startswith(PREFIJOS_STREAM)
        self.fps = FPS_POR_DEFECTO
        self._cap: Optional[cv2.VideoCapture] = None
        self._paused = False
        self._last_frame: Optional[np.ndarray] = None
        self._proximo: Optional[float] = None
        self._cola: queue.Queue = queue.Queue(maxsize=1)
        self._detener = threading.Event()
        self._terminado = threading.Event()
        self._hilo: Optional[threading.Thread] = None
        self._abrir()

    @property
    def paused(self) -> bool:
        return self._paused

    def read(self) -> tuple[bool, Optional[np.ndarray]]:
        if self._paused:
            time.sleep(1.0 / self.fps)
            return self._last_frame is not None, self._last_frame
        if self.es_stream:
            ok, frame = self._leer_stream()
        else:
            ok, frame = self._leer_archivo()
        if ok:
            self._last_frame = frame
        return ok, frame

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False
        self._proximo = None

    def restart(self) -> None:
        self._paused = False
        self._last_frame = None
        if self.es_stream:
            self._detener_hilo()
            self._liberar_captura()
            self._vaciar_cola()
            self._abrir()
        elif self._cap is not None:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            self._proximo = None

    def release(self) -> None:
        self._detener_hilo()
        self._liberar_captura()
        self._vaciar_cola()

    def __iter__(self) -> Iterator[np.ndarray]:
        while True:
            ok, frame = self.read()
            if not ok:
                return
            yield frame

    def __enter__(self) -> "VideoStream":
        return self

    def __exit__(self, *_exc) -> None:
        self.release()

    def _abrir(self) -> None:
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            cap.release()
            raise IOError(f"No se pudo abrir la fuente: {self.source}")
        self._cap = cap
        fps = cap.get(cv2.CAP_PROP_FPS)
        self.fps = fps if fps and fps > 1.0 else FPS_POR_DEFECTO
        self._proximo = None
        if self.es_stream:
            self._iniciar_hilo()

    def _liberar_captura(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def _vaciar_cola(self) -> None:
        while True:
            try:
                self._cola.get_nowait()
            except queue.Empty:
                return

    def _iniciar_hilo(self) -> None:
        self._detener.clear()
        self._terminado.clear()
        self._hilo = threading.Thread(target=self._leer_continuo, daemon=True)
        self._hilo.start()

    def _detener_hilo(self) -> None:
        self._detener.set()
        if self._hilo is not None:
            self._hilo.join(timeout=2.0)
            self._hilo = None

    def _leer_continuo(self) -> None:
        fallos = 0
        while not self._detener.is_set():
            ok, frame = self._cap.read()
            if ok:
                fallos = 0
                self._publicar(frame)
                continue
            fallos += 1
            if fallos > REINTENTOS_STREAM:
                logger.error("Stream perdido: %s", self.source)
                break
            time.sleep(0.5)
            self._cap.release()
            self._cap = cv2.VideoCapture(self.source)
        self._terminado.set()

    def _publicar(self, frame: np.ndarray) -> None:
        try:
            self._cola.put_nowait(frame)
        except queue.Full:
            try:
                self._cola.get_nowait()
            except queue.Empty:
                pass
            self._cola.put_nowait(frame)

    def _leer_stream(self) -> tuple[bool, Optional[np.ndarray]]:
        while not self._detener.is_set():
            try:
                return True, self._cola.get(timeout=0.5)
            except queue.Empty:
                if self._terminado.is_set():
                    break
        return False, None

    def _leer_archivo(self) -> tuple[bool, Optional[np.ndarray]]:
        if self._cap is None:
            return False, None
        intervalo = 1.0 / self.fps
        ahora = time.monotonic()
        if self._proximo is None or ahora - self._proximo > intervalo:
            self._proximo = ahora
        espera = self._proximo - ahora
        if espera > 0:
            time.sleep(espera)
        self._proximo += intervalo
        ok, frame = self._cap.read()
        if not ok and self.loop:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self._cap.read()
        if not ok:
            return False, None
        return True, frame