"""
Metricas de evaluacion, siempre en MINUTOS.

Nunca se reporta un error en escala logaritmica: no significa nada para un asesor.
Si un modelo predice en `log1p`, se deshace con `np.expm1` antes de medir.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def metricas(y_real_min, y_pred_min) -> dict:
    y = np.asarray(y_real_min, dtype=float)
    p = np.asarray(y_pred_min, dtype=float)
    err = p - y
    abs_err = np.abs(err)
    with np.errstate(divide="ignore", invalid="ignore"):
        ape = np.where(y > 0, abs_err / y, np.nan)
    return {
        "MAE_min": round(float(abs_err.mean()), 2),
        "MedAE_min": round(float(np.median(abs_err)), 2),
        "pct_dentro_5min": round(float((abs_err <= 5).mean() * 100), 2),
        "pct_dentro_15min": round(float((abs_err <= 15).mean() * 100), 2),
        "pct_dentro_30min": round(float((abs_err <= 30).mean() * 100), 2),
        "RMSE_min": round(float(np.sqrt((err ** 2).mean())), 2),
        "MAPE_pct": round(float(np.nanmean(ape) * 100), 2),
    }


def tabla_metricas(filas: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(filas)


def mejora_pct(mae_modelo: float, mae_referencia: float) -> float:
    """Mejora porcentual del MAE respecto a la referencia. Positiva = mejor."""
    return round(100 * (mae_referencia - mae_modelo) / mae_referencia, 2)
