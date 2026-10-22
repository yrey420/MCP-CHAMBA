"""Genera la hoja de vida en PDF a partir del perfil maestro.

uv run python generar_cv.py --idioma es
uv run python generar_cv.py --idioma en --etiquetas backend,integraciones,ia --salida salida/x.pdf
"""

from __future__ import annotations

import argparse
from pathlib import Path

from empleo import cv
from empleo.perfil import cargar, nombre_archivo
from empleo.rutas import PERFIL, SALIDA


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--idioma", choices=["es", "en"], default="es")
    parser.add_argument("--perfil", type=Path, default=PERFIL)
    parser.add_argument("--etiquetas", default="", help="ej: backend,integraciones,ia")
    parser.add_argument("--max-logros", type=int, default=None)
    parser.add_argument("--salida", type=Path, default=None)
    parser.add_argument("--html", action="store_true", help="guarda también el HTML")
    args = parser.parse_args()

    perfil = cargar(args.perfil)
    salida = args.salida or SALIDA / f"CV-{nombre_archivo(perfil)}-{args.idioma.upper()}.pdf"
    paginas = cv.generar(
        perfil,
        salida,
        idioma=args.idioma,
        etiquetas=[e.strip() for e in args.etiquetas.split(",") if e.strip()],
        max_logros=args.max_logros,
        guardar_html=args.html,
    )
    print(f"{salida} ({paginas} páginas)")


if __name__ == "__main__":
    main()
