"""
Utilidades comunes a todos los scripts del PFM.

Conexion de SOLO LECTURA a la base de datos de origen.
Los parametros de conexion se leen exclusivamente de `.env` (no versionado).
Ningun valor de conexion se escribe nunca en disco ni en los informes.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
FIGURAS = OUT / "figuras"

RANDOM_STATE = 42

_REQUERIDAS = ["BITRIX_HOST", "BITRIX_PORT", "BITRIX_USER", "BITRIX_PASS", "BITRIX_DB"]


def cargar_entorno() -> tuple[str, str]:
    """Carga .env y devuelve (fecha_desde, fecha_hasta)."""
    load_dotenv(ROOT / ".env")
    faltan = [k for k in _REQUERIDAS if not os.getenv(k)]
    if faltan:
        sys.exit(
            "Faltan variables de conexion en .env: "
            + ", ".join(faltan)
            + ". Copia .env.example a .env y rellenalo."
        )
    return (
        os.getenv("FECHA_DESDE", "2025-01-01"),
        os.getenv("FECHA_HASTA", "2026-08-01"),
    )


def motor():
    """Crea el engine SQLAlchemy. Solo se usa para SELECT."""
    cargar_entorno()
    url = (
        "mysql+pymysql://{u}:{p}@{h}:{port}/{db}?charset=utf8mb4".format(
            u=os.getenv("BITRIX_USER"),
            p=os.getenv("BITRIX_PASS"),
            h=os.getenv("BITRIX_HOST"),
            port=os.getenv("BITRIX_PORT", "3306"),
            db=os.getenv("BITRIX_DB"),
        )
    )
    return create_engine(url, pool_pre_ping=True)


def consulta(eng, sql: str, **params) -> pd.DataFrame:
    """Ejecuta un SELECT y devuelve un DataFrame. Aborta si no es SELECT."""
    lineas = [
        ln for ln in sql.strip().splitlines() if ln.strip() and not ln.strip().startswith("--")
    ]
    limpio = "\n".join(lineas).lstrip("(").lstrip()
    if not limpio.upper().startswith(("SELECT", "WITH", "SHOW", "DESCRIBE")):
        raise RuntimeError("Solo se permiten consultas de lectura.")
    with eng.connect() as con:
        return pd.read_sql(text(sql), con, params=params)


def asegurar_dirs() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    FIGURAS.mkdir(parents=True, exist_ok=True)


def md_tabla(df: pd.DataFrame, max_filas: int = 200) -> str:
    """DataFrame -> tabla markdown, sin indice."""
    if df.empty:
        return "_(sin filas)_\n"
    d = df.head(max_filas)
    return d.to_markdown(index=False) + "\n"
