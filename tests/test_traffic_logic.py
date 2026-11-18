import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.controller.traffic_logic import (  # noqa: E402
    EMERGENCY_OVERRIDE,
    MODO_ADAPTATIVO,
    MODO_FIJO,
    TrafficController,
    calcular_verde,
)

SIN_TRAFICO = {
    "Calle_A": {"autos": 0, "buses": 0},
    "Calle_B": {"autos": 0, "buses": 0},
}


@pytest.mark.parametrize(
    "autos, buses, esperado",
    [(0, 0, 15), (3, 0, 15), (10, 0, 30), (30, 0, 60), (5, 2, 28)],
)
def test_calcular_verde(autos, buses, esperado):
    assert calcular_verde(autos, buses) == esperado


def test_secuencia_normal_y_rojo():
    ctrl = TrafficController()
    estado = ctrl.tick(15.0, SIN_TRAFICO)
    assert estado.fase == "AMARILLO_A"
    assert estado.luz_A == "AMARILLO" and estado.luz_B == "ROJO"
    estado = ctrl.tick(3.0, SIN_TRAFICO)
    assert estado.fase == "VERDE_B"
    assert estado.luz_A == "ROJO" and estado.luz_B == "VERDE"
    assert estado.ciclo_completado_info.calle == "Calle_A"
    assert estado.ciclo_completado_info.segundos_rojo == 15 + 3


def test_modo_adaptativo_usa_conteos():
    ctrl = TrafficController()
    conteos = {"Calle_B": {"autos": 30, "buses": 0}}
    estado = ctrl.tick(18.0, conteos)
    assert estado.fase == "VERDE_B"
    assert estado.segundos_restantes == pytest.approx(60.0)


def test_modo_fijo_ignora_conteos():
    ctrl = TrafficController()
    assert ctrl.toggle_modo() == MODO_FIJO
    conteos = {"Calle_B": {"autos": 30, "buses": 0}}
    estado = ctrl.tick(18.0, conteos)
    assert estado.fase == "VERDE_B"
    assert estado.segundos_restantes == pytest.approx(30.0)
    assert estado.modo == MODO_FIJO
    assert ctrl.toggle_modo() == MODO_ADAPTATIVO


def test_emergencia_override_y_reanudacion():
    ctrl = TrafficController()
    ctrl.tick(0.0, SIN_TRAFICO)
    assert ctrl.emergencia() is True

    estado = ctrl.tick(0.0, SIN_TRAFICO)
    assert estado.fase == "AMARILLO_A"
    assert estado.es_emergencia is True
    assert estado.segundos_restantes == pytest.approx(3.0)

    estado = ctrl.tick(3.0, SIN_TRAFICO)
    assert estado.fase == EMERGENCY_OVERRIDE
    assert estado.luz_B == "VERDE" and estado.luz_A == "ROJO"
    assert estado.segundos_restantes == pytest.approx(15.0)
    assert estado.ciclo_completado_info.segundos_rojo == 15 + 3

    estado = ctrl.tick(15.0, SIN_TRAFICO)
    assert estado.fase == "AMARILLO_B"
    assert estado.es_emergencia is False

    estado = ctrl.tick(3.0, SIN_TRAFICO)
    assert estado.fase == "VERDE_A"
    assert estado.ciclo_completado_info.tipo_evento == EMERGENCY_OVERRIDE


def test_emergencia_antirebote():
    ctrl = TrafficController()
    assert ctrl.emergencia() is True
    antes = ctrl.tick(1.0, SIN_TRAFICO)
    assert ctrl.emergencia() is False
    despues = ctrl.tick(0.0, SIN_TRAFICO)
    assert despues.fase == antes.fase
    assert despues.segundos_restantes == pytest.approx(antes.segundos_restantes)


def test_emergencia_desde_verde_b_da_prioridad_a_a():
    ctrl = TrafficController()
    ctrl.tick(18.0, SIN_TRAFICO)
    ctrl.emergencia()
    estado = ctrl.tick(3.0, SIN_TRAFICO)
    assert estado.fase == EMERGENCY_OVERRIDE
    assert estado.luz_A == "VERDE" and estado.luz_B == "ROJO"