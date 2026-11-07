"""Dónde vive cada cosa.

Por defecto todo es relativo a la carpeta del proyecto, y cada ruta se puede cambiar con una
variable de entorno (útil para guardar tus datos fuera del repositorio):

    EMPLEO_PERFIL    perfil maestro (por defecto perfil/perfil.yaml)
    EMPLEO_EMPRESAS  portales de empresas seguidas (por defecto perfil/empresas.yaml)
    EMPLEO_SALIDA    hojas de vida, cartas y carpetas de postulación (por defecto salida/)
    EMPLEO_BASE      base SQLite de ofertas y postulaciones (por defecto datos/empleo.db)

Varias personas con el mismo código: con EMPLEO_PERSONA=ana se usan perfil/ana/perfil.yaml,
perfil/ana/empresas.yaml, salida/ana/ y datos/ana.db, sin mezclar sus datos con los de nadie.
Las variables de arriba siguen mandando sobre esas rutas.

Si no existe tu perfil (y no definiste EMPLEO_PERFIL ni EMPLEO_PERSONA), se usa
perfil/perfil.example.yaml, un perfil ficticio, para que el servidor arranque y puedas probarlo.
"""

import os
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

PERSONA = os.environ.get("EMPLEO_PERSONA", "").strip().lower()
if PERSONA and not re.fullmatch(r"[a-z0-9_-]+", PERSONA):
    raise ValueError("EMPLEO_PERSONA solo admite letras, números, guion y guion bajo.")


def _ruta(variable: str, defecto: Path) -> Path:
    valor = os.environ.get(variable)
    return Path(valor).expanduser() if valor else defecto


_PERFILES = RAIZ / "perfil" / PERSONA if PERSONA else RAIZ / "perfil"

PERFIL_EJEMPLO = RAIZ / "perfil" / "perfil.example.yaml"
PERFIL = _ruta("EMPLEO_PERFIL", _PERFILES / "perfil.yaml")
if not PERFIL.exists() and "EMPLEO_PERFIL" not in os.environ and not PERSONA:
    PERFIL = PERFIL_EJEMPLO

EMPRESAS = _ruta("EMPLEO_EMPRESAS", _PERFILES / "empresas.yaml")
PLANTILLAS = RAIZ / "plantillas"
SALIDA = _ruta("EMPLEO_SALIDA", RAIZ / "salida" / PERSONA if PERSONA else RAIZ / "salida")
POSTULACIONES = SALIDA / "postulaciones"
BASE = _ruta("EMPLEO_BASE", RAIZ / "datos" / f"{PERSONA or 'empleo'}.db")
