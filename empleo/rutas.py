"""Dónde vive cada cosa.

Por defecto todo es relativo a la carpeta del proyecto, y cada ruta se puede cambiar con una
variable de entorno (útil para guardar tus datos fuera del repositorio):

    EMPLEO_PERFIL    perfil maestro (por defecto perfil/perfil.yaml)
    EMPLEO_EMPRESAS  portales de empresas seguidas (por defecto perfil/empresas.yaml)
    EMPLEO_SALIDA    hojas de vida, cartas y carpetas de postulación (por defecto salida/)
    EMPLEO_BASE      base SQLite de ofertas y postulaciones (por defecto datos/empleo.db)

Si no existe tu perfil (y no definiste EMPLEO_PERFIL), se usa perfil/perfil.example.yaml,
un perfil ficticio, para que el servidor arranque y puedas probarlo.
"""

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def _ruta(variable: str, defecto: Path) -> Path:
    valor = os.environ.get(variable)
    return Path(valor).expanduser() if valor else defecto


PERFIL_EJEMPLO = RAIZ / "perfil" / "perfil.example.yaml"
PERFIL = _ruta("EMPLEO_PERFIL", RAIZ / "perfil" / "perfil.yaml")
if not PERFIL.exists() and "EMPLEO_PERFIL" not in os.environ:
    PERFIL = PERFIL_EJEMPLO

EMPRESAS = _ruta("EMPLEO_EMPRESAS", RAIZ / "perfil" / "empresas.yaml")
PLANTILLAS = RAIZ / "plantillas"
SALIDA = _ruta("EMPLEO_SALIDA", RAIZ / "salida")
POSTULACIONES = SALIDA / "postulaciones"
BASE = _ruta("EMPLEO_BASE", RAIZ / "datos" / "empleo.db")
