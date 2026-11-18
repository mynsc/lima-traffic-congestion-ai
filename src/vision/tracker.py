from __future__ import annotations

import time
from collections import deque
from typing import TYPE_CHECKING, Callable, Iterable, Optional

if TYPE_CHECKING:
    from src.vision.detector import Detection

CALLES_POR_DEFECTO = ("Calle_A", "Calle_B")


class ROISnapshotTracker:
    def __init__(
        self,
        ventana: float = 3.0,
        clock: Callable[[], float] = time.monotonic,
        calles: Iterable[str] = CALLES_POR_DEFECTO,
    ) -> None:
        self.ventana = ventana
        self._clock = clock
        self._eventos = {calle: deque() for calle in calles}
        self._maximos = {calle: self._vacio() for calle in self._eventos}

    @staticmethod
    def _vacio() -> dict:
        return {"autos": 0, "buses": 0}

    def update(
        self, detecciones: Iterable[Detection], ahora: Optional[float] = None
    ) -> None:
        ahora = self._clock() if ahora is None else ahora
        for det in detecciones:
            if det.track_id is None or det.calle not in self._eventos:
                continue
            self._eventos[det.calle].append((ahora, det.track_id, det.clase))
        for calle in self._eventos:
            self._purgar(calle, ahora)
            actual = self._contar(calle)
            maximo = self._maximos[calle]
            maximo["autos"] = max(maximo["autos"], actual["autos"])
            maximo["buses"] = max(maximo["buses"], actual["buses"])

    def conteo_actual(self, ahora: Optional[float] = None) -> dict:
        ahora = self._clock() if ahora is None else ahora
        resultado = {}
        for calle in self._eventos:
            self._purgar(calle, ahora)
            resultado[calle] = self._contar(calle)
        return resultado

    def maximos(self) -> dict:
        return {calle: dict(valores) for calle, valores in self._maximos.items()}

    def reiniciar(self, calle: Optional[str] = None) -> None:
        calles = list(self._eventos) if calle is None else [calle]
        for nombre in calles:
            if nombre in self._eventos:
                self._eventos[nombre].clear()
                self._maximos[nombre] = self._vacio()

    def _purgar(self, calle: str, ahora: float) -> None:
        eventos = self._eventos[calle]
        while eventos and ahora - eventos[0][0] > self.ventana:
            eventos.popleft()

    def _contar(self, calle: str) -> dict:
        eventos = self._eventos[calle]
        autos = {tid for _, tid, clase in eventos if clase == "car"}
        buses = {tid for _, tid, clase in eventos if clase == "bus"}
        return {"autos": len(autos), "buses": len(buses)}