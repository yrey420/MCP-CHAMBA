"""La hoja de vida en PDF, armada desde el perfil maestro.

Una sola columna y texto real, sin tablas ni imágenes: así la leen bien los
filtros automáticos de las empresas (ATS). Con `etiquetas` se ponen primero los
logros que más se parecen a la oferta; `titular` y `resumen` permiten una
versión adaptada (siempre con hechos del perfil).
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from empleo.perfil import texto
from empleo.rutas import PLANTILLAS

# WeasyPrint narra cada paso del PDF; en el MCP solo interesan los problemas.
logging.getLogger("weasyprint").setLevel(logging.WARNING)
logging.getLogger("fontTools").setLevel(logging.WARNING)

MESES = {
    "es": [
        "Ene",
        "Feb",
        "Mar",
        "Abr",
        "May",
        "Jun",
        "Jul",
        "Ago",
        "Sep",
        "Oct",
        "Nov",
        "Dic",
    ],
    "en": [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ],
}
TEXTOS = {
    "es": {
        "resumen": "Perfil",
        "habilidades": "Habilidades",
        "experiencia": "Experiencia",
        "proyectos": "Proyectos",
        "educacion": "Educación e idiomas",
        "presente": "Presente",
    },
    "en": {
        "resumen": "Summary",
        "habilidades": "Skills",
        "experiencia": "Experience",
        "proyectos": "Projects",
        "educacion": "Education & languages",
        "presente": "Present",
    },
}


def mes(valor, idioma: str) -> str:
    if not valor:
        return TEXTOS[idioma]["presente"]
    if isinstance(valor, date):
        anio, numero = valor.year, valor.month
    else:
        partes = str(valor).split("-")
        if len(partes) == 1:  # solo el año, cuando no se sabe el mes
            return partes[0]
        anio, numero = (int(x) for x in partes[:2])
    return f"{MESES[idioma][numero - 1]} {anio}"


def preparar(
    perfil: dict,
    idioma: str,
    etiquetas: list[str] | None = None,
    max_logros: int | None = None,
    titular: str | None = None,
    resumen: str | None = None,
) -> dict:
    """El perfil, ya en un idioma y con lo más relevante primero."""
    etiquetas = etiquetas or []

    # Las primeras etiquetas pesan más: son lo que la oferta pide primero.
    pesos = {e: len(etiquetas) - i for i, e in enumerate(etiquetas)}

    def relevancia(logro: dict) -> int:
        return sum(pesos.get(e, 0) for e in logro.get("etiquetas", []))

    experiencia = []
    for trabajo in perfil["experiencia"]:
        logros = trabajo.get("logros", [])
        if etiquetas:
            # Orden estable: a igual relevancia, se respeta el orden del perfil.
            logros = sorted(logros, key=relevancia, reverse=True)
        if max_logros:
            logros = logros[:max_logros]
        experiencia.append(
            {
                "empresa": texto(trabajo["empresa"], idioma),
                "cargo": texto(trabajo["cargo"], idioma),
                "fechas": f"{mes(trabajo['inicio'], idioma)} – {mes(trabajo.get('fin'), idioma)}",
                "contexto": texto(trabajo.get("contexto", ""), idioma),
                "logros": [texto(lo, idioma) for lo in logros],
            }
        )

    proyectos = [
        {
            "nombre": p["nombre"],
            "tipo": texto(p.get("tipo", ""), idioma),
            "fechas": texto(p.get("fechas", ""), idioma),
            "texto": texto(p, idioma),
        }
        for p in perfil.get("proyectos", [])
        if p.get("incluir") is True
    ]

    datos = perfil["datos"]
    return {
        "idioma": idioma,
        "t": TEXTOS[idioma],
        "nombre": datos["nombre"],
        "titular": titular or texto(perfil["titular"], idioma),
        "contacto": [
            texto(datos["ciudad"], idioma),
            datos["telefono"],
            datos["correo"],
        ],
        "linkedin": datos.get("linkedin"),
        "github": datos.get("github"),
        "resumen": resumen or texto(perfil["resumen"], idioma),
        "habilidades": [
            {
                "grupo": texto(h["grupo"], idioma),
                "items": [texto(i, idioma) for i in h["items"]],
            }
            for h in perfil["habilidades"]
        ],
        "experiencia": experiencia,
        "proyectos": proyectos,
        "educacion": [
            {
                "titulo": texto(e["titulo"], idioma),
                "institucion": e["institucion"],
                "fechas": e["fechas"],
            }
            for e in perfil["educacion"]
        ],
        "idiomas": [texto(i, idioma) for i in datos["idiomas"]],
    }


def _entorno() -> Environment:
    return Environment(loader=FileSystemLoader(PLANTILLAS), autoescape=select_autoescape(["html"]))


def generar(
    perfil: dict,
    salida: Path,
    idioma: str = "es",
    etiquetas: list[str] | None = None,
    max_logros: int | None = None,
    titular: str | None = None,
    resumen: str | None = None,
    guardar_html: bool = False,
) -> int:
    """Escribe el PDF y devuelve cuántas páginas quedó."""
    from weasyprint import HTML  # carga pesada: solo cuando se genera

    contexto = preparar(perfil, idioma, etiquetas, max_logros, titular, resumen)
    html = _entorno().get_template("cv.html").render(**contexto)
    salida.parent.mkdir(parents=True, exist_ok=True)
    if guardar_html:
        salida.with_suffix(".html").write_text(html, encoding="utf-8")
    documento = HTML(string=html, base_url=str(PLANTILLAS)).render()
    documento.write_pdf(salida)
    return len(documento.pages)


def generar_carta(perfil: dict, salida: Path, cuerpo: str, idioma: str = "es") -> None:
    """La carta de presentación en PDF, con el mismo encabezado de la hoja de vida."""
    from weasyprint import HTML

    datos = perfil["datos"]
    html = (
        _entorno()
        .get_template("carta.html")
        .render(
            idioma=idioma,
            nombre=datos["nombre"],
            titular=texto(perfil["titular"], idioma),
            contacto=[
                texto(datos["ciudad"], idioma),
                datos["telefono"],
                datos["correo"],
            ],
            linkedin=datos.get("linkedin"),
            parrafos=[p.strip() for p in cuerpo.strip().split("\n\n") if p.strip()],
        )
    )
    salida.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(PLANTILLAS)).write_pdf(salida)
