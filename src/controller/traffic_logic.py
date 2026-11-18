# src/controller/traffic_logic.py
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from config.settings import (
    AMARILLO,
    BASE_VERDE,
    PESO_AUTO,
    PESO_BUS,
    VERDE_EMERGENCIA,
    VERDE_FIJO,
    VERDE_MAX,
    VERDE_MIN,
)

MODO_ADAPTATIVO = "ADAPTATIVO"
MODO_FIJO = "FIJO"
EMERGENCY_OVERRIDE = "EMERGENCY_OVERRIDE"
TIPO_NORMAL = "NORMAL"


def calcular_verde(autos: int, buses: int) -> int:
    bruto = autos * PESO_AUTO + buses * PESO_BUS + BASE_VERDE
    acotado = min(max(bruto, VERDE_MIN), VERDE_MAX)
    return int(math.floor(acotado + 0.5))


def _opuesta(calle: str) -> str:
    return "B" if calle == "A" else "A"


@dataclass(frozen=True)
class CicloInfo:
    calle: str
    fase_inicio: str
    segundos_verde: int
    segundos_rojo: int
    modo: str
    tipo_evento: str
    autos: int
    buses: int


@dataclass(frozen=True)
class EstadoSemaforo:
    fase: str
    luz_A: str
    luz_B: str
    segundos_restantes: float
    modo: str
    es_emergencia: bool
    ciclo_completado_info: Optional[CicloInfo] = None


class TrafficController:
    def __init__(self, modo: str = MODO_ADAPTATIVO) -> None:
        self.modo = modo
        self._emergencia = False
        self._override_pendiente = False
        self._fase = ""
        self._calle = "A"
        self._restante = 0.0
        self._duracion = 0.0
        self._verde = 0
        self._tipo = TIPO_NORMAL
        self._autos = 0
        self._buses = 0
        self._inicio = ""
        self._iniciar_verde("VERDE_A", "A", self._verde_para(0, 0), TIPO_NORMAL, 0, 0)

    def toggle_modo(self) -> str:
        self.modo = MODO_FIJO if self.modo == MODO_ADAPTATIVO else MODO_ADAPTATIVO
        return self.modo

    def emergencia(self) -> bool:
        if self._emergencia:
            return False
        self._emergencia = True
        self._override_pendiente = True
        if self._fase.startswith("VERDE"):
            self._verde = int(self._duracion - self._restante)
            self._entrar_fase(f"AMARILLO_{self._calle}", self._calle, AMARILLO)
        return True

    def tick(self, dt: float, conteos: dict) -> EstadoSemaforo:
        pendiente = max(dt, 0.0)
        info: Optional[CicloInfo] = None
        while pendiente >= self._restante:
            pendiente -= self._restante
            self._restante = 0.0
            nuevo = self._avanzar(conteos)
            if nuevo is not None:
                info = nuevo
        self._restante -= pendiente
        return self._estado(info)

    def _verde_para(self, autos: int, buses: int) -> int:
        if self.modo == MODO_FIJO:
            return VERDE_FIJO
        return calcular_verde(autos, buses)

    @staticmethod
    def _leer(conteos: dict, calle: str) -> tuple[int, int]:
        datos = conteos.get(f"Calle_{calle}", {})
        return int(datos.get("autos", 0)), int(datos.get("buses", 0))

    def _entrar_fase(self, fase: str, calle: str, segundos: float) -> None:
        self._fase = fase
        self._calle = calle
        self._restante = float(segundos)
        self._duracion = float(segundos)

    def _iniciar_verde(
        self,
        fase: str,
        calle: str,
        segundos: int,
        tipo: str,
        autos: int,
        buses: int,
    ) -> None:
        self._entrar_fase(fase, calle, segundos)
        self._verde = segundos
        self._tipo = tipo
        self._autos = autos
        self._buses = buses
        self._inicio = datetime.now().isoformat(timespec="seconds")

    def _info(self, segundos_rojo: int) -> CicloInfo:
        return CicloInfo(
            calle=f"Calle_{self._calle}",
            fase_inicio=self._inicio,
            segundos_verde=self._verde,
            segundos_rojo=segundos_rojo,
            modo=self.modo,
            tipo_evento=self._tipo,
            autos=self._autos,
            buses=self._buses,
        )

    def _avanzar(self, conteos: dict) -> Optional[CicloInfo]:
        calle = self._calle
        if self._fase == EMERGENCY_OVERRIDE:
            self._emergencia = False
            self._entrar_fase(f"AMARILLO_{calle}", calle, AMARILLO)
            return None
        if self._fase.startswith("VERDE"):
            self._entrar_fase(f"AMARILLO_{calle}", calle, AMARILLO)
            return None
        return self._fin_amarillo(conteos)

    def _fin_amarillo(self, conteos: dict) -> CicloInfo:
        otra = _opuesta(self._calle)
        autos, buses = self._leer(conteos, otra)
        if self._override_pendiente:
            self._override_pendiente = False
            segundos, tipo, fase = VERDE_EMERGENCIA, EMERGENCY_OVERRIDE, None
            fase = EMERGENCY_OVERRIDE
        else:
            segundos = self._verde_para(autos, buses)
            tipo, fase = TIPO_NORMAL, f"VERDE_{otra}"
        info = self._info(segundos + AMARILLO)
        self._iniciar_verde(fase, otra, segundos, tipo, autos, buses)
        return info

    def _estado(self, info: Optional[CicloInfo]) -> EstadoSemaforo:
        activa = "AMARILLO" if self._fase.startswith("AMARILLO") else "VERDE"
        luces = {"A": "ROJO", "B": "ROJO"}
        luces[self._calle] = activa
        return EstadoSemaforo(
            fase=self._fase,
            luz_A=luces["A"],
            luz_B=luces["B"],
            segundos_restantes=max(self._restante, 0.0),
            modo=self.modo,
            es_emergencia=self._emergencia,
            ciclo_completado_info=info,
        )