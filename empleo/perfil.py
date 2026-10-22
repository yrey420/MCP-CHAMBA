"""El perfil maestro (perfil/perfil.yaml): la única fuente de verdad sobre la persona que
busca empleo. Ver perfil/perfil.example.yaml para el formato."""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import Path

import yaml

from empleo import rutas


def cargar(ruta: Path | None = None) -> dict:
    ruta = ruta or rutas.PERFIL  # se lee al usar: las pruebas y EMPLEO_PERFIL la cambian
    return yaml.safe_load(ruta.read_text(encoding="utf-8"))


def es_de_ejemplo(ruta: Path | None = None) -> bool:
    """¿Se está usando el perfil ficticio de ejemplo?"""
    return (ruta or rutas.PERFIL).resolve() == rutas.PERFIL_EJEMPLO.resolve()


def nombre_archivo(perfil: dict) -> str:
    """«Ana María Pérez» → «Ana-Maria-Perez», para nombrar los PDF."""
    datos = perfil.get("datos", {})
    nombre = datos.get("nombre_corto") or datos.get("nombre") or "perfil"
    limpio = unicodedata.normalize("NFKD", nombre)
    limpio = "".join(c for c in limpio if not unicodedata.combining(c))
    return re.sub(r"[^A-Za-z0-9]+", "-", limpio).strip("-") or "perfil"


def ciudad_base(perfil: dict) -> str:
    """La ciudad donde vive (para saber si un trabajo presencial le queda cerca):
    `objetivo.ciudad` o, si no está, lo que va antes de la primera coma en `datos.ciudad`."""
    ciudad = (perfil.get("objetivo") or {}).get("ciudad")
    if not ciudad:
        ciudad = texto((perfil.get("datos") or {}).get("ciudad", "")).split(",")[0]
    return ciudad.strip()


def salida_ultimo_empleo(perfil: dict):
    """Cómo contar la salida del último empleo, si el perfil lo dice. Acepta
    `salida_ultimo_empleo` o cualquier clave que empiece por `salida_`."""
    if "salida_ultimo_empleo" in perfil:
        return perfil["salida_ultimo_empleo"]
    return next((v for k, v in perfil.items() if k.startswith("salida_")), None)


def texto(valor, idioma: str = "es") -> str:
    """Los campos bilingües son {es, en}; un texto «es|en» también vale."""
    if isinstance(valor, dict):
        return valor.get(idioma) or valor.get("es") or ""
    valor = "" if valor is None else str(valor)
    if "|" in valor:
        es, en = valor.split("|", 1)
        return en if idioma == "en" else es
    return valor


def anios_de_experiencia(perfil: dict, hoy: date | None = None) -> float:
    """Desde el primer trabajo hasta hoy (o hasta el último, si no hay uno actual)."""
    hoy = hoy or date.today()
    inicios = [_fecha(t["inicio"]) for t in perfil["experiencia"]]
    return round((hoy - min(inicios)).days / 365.25, 1)


def _fecha(valor) -> date:
    if isinstance(valor, date):
        return valor
    partes = [int(x) for x in str(valor).split("-")[:2]]
    return date(partes[0], partes[1] if len(partes) > 1 else 1, 1)


def resumen_para_el_agente(perfil: dict) -> dict:
    """Lo que el asistente necesita para escribir cartas y adaptar textos sin
    inventar nada: solo hechos del perfil."""
    return {
        "nombre": perfil["datos"]["nombre"],
        "contacto": {
            "ciudad": texto(perfil["datos"]["ciudad"]),
            "correo": perfil["datos"]["correo"],
            "telefono": perfil["datos"]["telefono"],
            "linkedin": perfil["datos"]["linkedin"],
        },
        "idiomas": [texto(i) for i in perfil["datos"]["idiomas"]],
        "objetivo": perfil["objetivo"],
        "titular": perfil["titular"],
        "resumen": perfil["resumen"],
        "habilidades": {
            texto(h["grupo"]): [texto(i) for i in h["items"]] for h in perfil["habilidades"]
        },
        "experiencia": [
            {
                "empresa": texto(t["empresa"]),
                "cargo": texto(t["cargo"]),
                "desde": str(t["inicio"]),
                "hasta": str(t.get("fin") or "presente"),
                "contexto": texto(t.get("contexto", "")),
                "logros": [
                    {"es": lo["es"], "en": lo["en"], "etiquetas": lo["etiquetas"]}
                    for lo in t["logros"]
                ],
            }
            for t in perfil["experiencia"]
        ],
        "proyectos": [
            {"nombre": p["nombre"], "es": p["es"], "en": p["en"]}
            for p in perfil.get("proyectos", [])
            if p.get("incluir") is True
        ],
        "educacion": [
            f"{texto(e['titulo'])} — {e['institucion']} ({e['fechas']})"
            for e in perfil["educacion"]
        ],
        "historias": perfil.get("historias", []),
        "salida_ultimo_empleo": salida_ultimo_empleo(perfil),
        "reglas_para_el_asistente": perfil.get("reglas_para_el_asistente", []),
        "decisiones": perfil.get("decisiones", []),
    }
