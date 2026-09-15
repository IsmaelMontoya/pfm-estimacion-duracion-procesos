"""
Comprobacion de seguridad previa a cada commit (ver README, seccion Seguridad).

Revisa los archivos que git tiene preparados o versionados bajo el directorio del
PFM y aborta con codigo 1 si aparece alguno de los patrones prohibidos.

Uso:  py src/_check_seguridad.py [--staged]
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(
    subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()
)
RELATIVO = ROOT.relative_to(REPO).as_posix() if ROOT != REPO else "."
PREFIJO = "" if RELATIVO == "." else RELATIVO + "/"

PATRONES = [
    ("ip", re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")),
    # se excluye el patron seguro password=os.environ[...]: es precisamente la
    # forma recomendada de cargar credenciales (ver Seguridad en el README)
    ("credencial", re.compile(r"(password|passwd|pwd)\s*=\s*(?!os\.environ)", re.IGNORECASE)),
    # nombres reales, no el nombre generico del producto Biloop (que si se cita
    # como sistema, igual que se cita Bitrix, sin ser un dato sensible)
    ("nombre_bd", re.compile(r"(sitemanager|servidor1\.biloop\.es)", re.IGNORECASE)),
]

# Archivo que contiene los patrones porque los DEFINE, no porque filtre nada:
# este mismo script. No forma parte del entregable propiamente dicho.
EXCLUIR_ARCHIVO = {"src/_check_seguridad.py"}

EXT_PROHIBIDAS = {".csv", ".parquet", ".pkl", ".joblib"}


def archivos() -> list[str]:
    modo = "--cached" if "--staged" in sys.argv else None
    cmd = ["git", "-C", str(REPO), "diff", "--name-only", "--cached"] if modo else [
        "git", "-C", str(REPO), "ls-files", RELATIVO
    ]
    salida = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return [f for f in salida.splitlines() if f.startswith(PREFIJO)]


def revisar_historial() -> int:
    """Aplica los mismos patrones a las lineas ANADIDAS en todo el historial del PFM."""
    salida = subprocess.run(
        ["git", "-C", str(REPO), "log", "-p", "--unified=0", "--", RELATIVO],
        capture_output=True, text=True, encoding="utf-8", errors="ignore", check=True,
    ).stdout
    fallos, archivo, commit = [], "", ""
    for linea in salida.splitlines():
        if linea.startswith("commit "):
            commit = linea.split()[1][:8]
        elif linea.startswith("+++ b/"):
            archivo = linea[6:]
            if PREFIJO and archivo.startswith(PREFIJO):
                archivo = archivo[len(PREFIJO):]
        elif linea.startswith("+") and not linea.startswith("+++"):
            if archivo in EXCLUIR_ARCHIVO:
                continue
            for etiqueta, patron in PATRONES:
                m = patron.search(linea)
                if m:
                    fallos.append(f"{commit} {archivo}: '{etiqueta}' -> {m.group(0)[:40]}")
    if fallos:
        print("COMPROBACION 7.3 SOBRE EL HISTORIAL FALLIDA:")
        for x in sorted(set(fallos)):
            print("  " + x)
        return 1
    print("Comprobacion 7.3 sobre el historial correcta.")
    return 0


def main() -> int:
    if "--historial" in sys.argv:
        return revisar_historial()
    fallos: list[str] = []
    for f in archivos():
        rel = f[len(PREFIJO):]
        ruta = REPO / f
        if rel == ".env" or rel.endswith("/.env"):
            fallos.append(f"{rel}: archivo .env versionado")
            continue
        if Path(rel).suffix.lower() in EXT_PROHIBIDAS:
            fallos.append(f"{rel}: extension de datos prohibida")
            continue
        if rel in EXCLUIR_ARCHIVO or not ruta.exists():
            continue
        try:
            texto = ruta.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for etiqueta, patron in PATRONES:
            m = patron.search(texto)
            if m:
                linea = texto[: m.start()].count("\n") + 1
                fallos.append(f"{rel}:{linea}: patron '{etiqueta}' -> {m.group(0)[:40]}")

    if fallos:
        print("COMPROBACION 7.3 FALLIDA:")
        for x in fallos:
            print("  " + x)
        return 1
    print(f"Comprobacion 7.3 correcta sobre {len(archivos())} archivos versionados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
