import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import AMARILLO, DB_PATH, ROIS  # noqa: E402
from src.controller.traffic_logic import (  # noqa: E402
    EMERGENCY_OVERRIDE,
    MODO_ADAPTATIVO,
    MODO_FIJO,
)
from src.database.repository import obtener_ultimos_ciclos  # noqa: E402

LIMITE_CICLOS = 20000
COLUMNAS_TABLA = [
    "id_ciclo",
    "calle",
    "fase_inicio",
    "segundos_verde_asignados",
    "modo",
    "tipo_evento",
    "cantidad_autos",
    "cantidad_buses",
    "segundos_rojo",
    "espera_promedio_seg",
]


def abrir_solo_lectura() -> sqlite3.Connection:
    ruta = Path(DB_PATH)
    if not ruta.exists():
        raise FileNotFoundError(ruta)
    conn = sqlite3.connect(f"{ruta.resolve().as_uri()}?mode=ro", uri=True)
    conn.execute("PRAGMA query_only=ON;")
    return conn


def cargar_ciclos() -> pd.DataFrame:
    try:
        conn = abrir_solo_lectura()
    except (FileNotFoundError, sqlite3.Error):
        return pd.DataFrame()
    try:
        df = obtener_ultimos_ciclos(conn, LIMITE_CICLOS)
    finally:
        conn.close()
    if df.empty:
        return df
    df["inicio"] = pd.to_datetime(df["fase_inicio"])
    df["vehiculos"] = df["cantidad_autos"] + df["cantidad_buses"]
    df["duracion_seg"] = df["segundos_verde_asignados"] + AMARILLO
    return df.sort_values("id_ciclo").reset_index(drop=True)


def filtrar(df: pd.DataFrame, calles: list, rango) -> pd.DataFrame:
    if df.empty:
        return df
    fechas = tuple(rango) if isinstance(rango, (tuple, list)) else (rango,)
    if not fechas:
        return df[df["calle"].isin(calles)]
    desde, hasta = fechas[0], fechas[-1]
    dias = df["inicio"].dt.date
    mascara = df["calle"].isin(calles) & (dias >= desde) & (dias <= hasta)
    return df[mascara]


def comparar_modos(df: pd.DataFrame) -> pd.DataFrame:
    normales = df[df["tipo_evento"] != EMERGENCY_OVERRIDE]
    if normales.empty:
        return pd.DataFrame()
    agrupado = normales.groupby("modo").agg(
        ciclos=("id_ciclo", "count"),
        espera_promedio_seg=("espera_promedio_seg", "mean"),
        vehiculos=("vehiculos", "sum"),
        duracion_seg=("duracion_seg", "sum"),
    )
    agrupado["vehiculos_por_min"] = agrupado["vehiculos"] / (
        agrupado["duracion_seg"] / 60
    )
    orden = [m for m in (MODO_ADAPTATIVO, MODO_FIJO) if m in agrupado.index]
    return agrupado.loc[orden].round(2)


def mostrar_kpis(df: pd.DataFrame) -> None:
    columnas = st.columns(4)
    columnas[0].metric("Ciclos", f"{len(df):,}")
    columnas[1].metric("Vehículos", f"{int(df['vehiculos'].sum()):,}")
    columnas[2].metric("Espera promedio (s)", f"{df['espera_promedio_seg'].mean():.1f}")
    columnas[3].metric(
        "Verde promedio (s)", f"{df['segundos_verde_asignados'].mean():.1f}"
    )


def mostrar_graficos(df: pd.DataFrame) -> None:
    izquierda, derecha = st.columns(2)
    with izquierda:
        st.subheader("Vehículos por ciclo y clase")
        st.bar_chart(
            df.tail(60),
            x="id_ciclo",
            y=["cantidad_autos", "cantidad_buses"],
            color=["#2ca02c", "#1f77b4"],
        )
    with derecha:
        st.subheader("Espera promedio acumulada (s)")
        acumulada = df[["inicio", "espera_promedio_seg"]].copy()
        acumulada["espera_acumulada"] = acumulada["espera_promedio_seg"].expanding().mean()
        st.line_chart(acumulada, x="inicio", y="espera_acumulada")


def mostrar_emergencias(df: pd.DataFrame) -> None:
    st.subheader("Emergencias")
    emergencias = df[df["tipo_evento"] == EMERGENCY_OVERRIDE]
    izquierda, derecha = st.columns([1, 2])
    izquierda.metric("Eventos de emergencia", len(emergencias))
    if emergencias.empty:
        derecha.caption("Sin emergencias en el periodo seleccionado.")
    else:
        derecha.bar_chart(emergencias.groupby("calle").size().rename("emergencias"))


def mostrar_comparativa(df: pd.DataFrame) -> None:
    st.subheader("ADAPTATIVO vs FIJO (sin emergencias)")
    comparativa = comparar_modos(df)
    if comparativa.empty:
        st.info("Sin datos suficientes para comparar modos.")
        return
    st.dataframe(
        comparativa[["ciclos", "espera_promedio_seg", "vehiculos_por_min"]]
    )
    izquierda, derecha = st.columns(2)
    izquierda.caption("Espera promedio (s)")
    izquierda.bar_chart(comparativa["espera_promedio_seg"])
    derecha.caption("Vehículos atendidos por minuto")
    derecha.bar_chart(comparativa["vehiculos_por_min"])


@st.fragment(run_every=5)
def panel() -> None:
    df = filtrar(
        cargar_ciclos(),
        st.session_state["f_calles"],
        st.session_state["f_fechas"],
    )
    st.caption(f"Última actualización: {datetime.now():%H:%M:%S}")
    if df.empty:
        st.info("Sin datos para los filtros seleccionados.")
        return
    mostrar_kpis(df)
    mostrar_graficos(df)
    mostrar_emergencias(df)
    mostrar_comparativa(df)
    with st.expander("Últimos ciclos"):
        st.dataframe(df.tail(20).iloc[::-1][COLUMNAS_TABLA])


st.set_page_config(page_title="Smart Traffic Lima", layout="wide")
st.title("Smart Traffic Lima - Dashboard")

if "f_fechas" not in st.session_state:
    iniciales = cargar_ciclos()
    hoy = date.today()
    minimo = hoy if iniciales.empty else iniciales["inicio"].min().date()
    st.session_state["f_fechas"] = (min(minimo, hoy), hoy)

st.sidebar.header("Filtros")
st.sidebar.multiselect(
    "Calles", options=list(ROIS), default=list(ROIS), key="f_calles"
)
st.sidebar.date_input("Rango de fechas", key="f_fechas")
st.sidebar.caption("Actualización automática cada 5 s (solo lectura)")

panel()