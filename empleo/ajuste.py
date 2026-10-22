"""Qué tan bien encaja una oferta con el perfil, de 0 a 100, y por qué.

El puntaje suma cuatro cosas: tecnologías (45), el rol (25), el nivel (10) y
si puede trabajar desde Colombia (20). Después resta lo que pesa en contra:
pedir muchos más años de experiencia o pagar menos de lo que se espera. Lo
importante no es el número sino las razones: con ellas se decide y se adapta
la hoja de vida.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from empleo.vocabulario import (
    DOMINA,
    ETIQUETA_DE,
    LENGUAJES_AJENOS,
    LENGUAJES_SUYOS,
    PARIENTES,
    nombre,
    normalizar,
    tecnologias_en,
)

# Súbelo al cambiar las reglas: las ofertas guardadas se vuelven a calificar.
VERSION = 4

# Tasas aproximadas a dólares (8 de octubre de 2026). Solo para comparar rangos.
USD_POR = {
    "USD": 1.0,
    "EUR": 1.12,
    "GBP": 1.3,
    "CAD": 0.73,
    "COP": 1 / 3236.84,
    "MXN": 0.055,
}
HORAS_AL_MES = 160

ROL_FUERTE = re.compile(
    r"back[- ]?end|full[- ]?stack|\bpython\b|\bdjango\b|\bjava\b(?!\s*script)|\bspring\b|\bapi\b|"
    r"integration|integracion|\berp\b|platform|plataforma|\bnode\b|\bphp\b|\blaravel\b|"
    r"\bai engineer|\bllm\b|agentic|\bai developer|ingenier[oa] de (ia|inteligencia artificial)"
)
ROL_GENERICO = re.compile(
    r"software (engineer|developer)|\bdeveloper\b|desarrollador|programador|ingenier[oa] de software|"
    r"\bengineer\b|devops|\bsre\b"
)
ROL_OTRO = re.compile(
    r"front[- ]?end|\bmobile\b|\bios\b|\bandroid\b|data scien|data analyst|analista de datos|\bqa\b|"
    r"tester|designer|\bux\b|\bui\b|product manager|project manager|\bsales\b|account (executive|manager)|"
    r"marketing|support|soporte|help ?desk|recruit|reclutador|machine learning"
)
NIVEL_BUENO = re.compile(r"\bsenior\b|\bsr\.?\b|semi[- ]?senior|\bssr\b|\bmid\b|\bii\b|\biii\b")
NIVEL_ALTO = re.compile(r"\blead\b|\bstaff\b|\bprincipal\b|\barchitect\b|arquitect[oa]|\bhead\b")
NIVEL_BAJO = re.compile(r"\bjunior\b|\bjr\.?\b|\bintern\b|trainee|practicante|pasante")

GEO_OK = re.compile(
    r"worldwide|anywhere|\bglobal\b|latam|latin ?america|latinoamerica|south america|americas|"
    r"colombia|bogota|bucaramanga|medellin|\bcali\b|utc-5|^remote$|^remoto$|fully remote|fully_remote"
)
GEO_RESTRINGIDA = re.compile(
    r"united states|\busa\b|\bus\b|u\.s\.|\bcanada\b|united kingdom|\buk\b|europe|\beu\b|\bemea\b|"
    r"germany|deutschland|berlin|france|spain|espana|\bindia\b|\bapac\b|australia|mexico|brazil|brasil|"
    r"argentina|chile|peru|uruguay|poland|portugal|netherlands"
)
SOLO_ALLA = re.compile(
    r"must (be|reside|live)[^.]{0,40}\b(in|within) (the )?(us|u\.s\.|united states|canada|uk|europe|eu)\b|"
    r"(us|u\.s\.) citizens?|authorized to work in the (us|u\.s\.|united states)|security clearance|"
    r"\bw-?2\b"
)
ANIOS = re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?(?:years?|yrs|anos)")

ESPANOL = re.compile(r"\b(de|la|que|el|en|los|para|con|una|del|las|por)\b")
INGLES = re.compile(r"\b(the|and|to|of|with|for|you|our|will|are|we)\b")


@dataclass
class Analisis:
    puntaje: int
    razones: list[str] = field(default_factory=list)
    coinciden: list[str] = field(default_factory=list)
    parecidas: list[str] = field(default_factory=list)
    faltan: list[str] = field(default_factory=list)
    etiquetas_cv: list[str] = field(default_factory=list)
    idioma: str = "en"
    remoto_desde_colombia: str = "desconocido"  # si | no | desconocido
    salario_usd_mes: tuple[float, float] | None = None

    def como_dict(self) -> dict:
        return {
            "version": VERSION,
            "puntaje": self.puntaje,
            "razones": self.razones,
            "coinciden": self.coinciden,
            "parecidas": self.parecidas,
            "faltan": self.faltan,
            "etiquetas_cv": self.etiquetas_cv,
            "idioma": self.idioma,
            "remoto_desde_colombia": self.remoto_desde_colombia,
            "salario_usd_mes": list(self.salario_usd_mes) if self.salario_usd_mes else None,
        }


def idioma_de(texto: str) -> str:
    limpio = normalizar(texto)[:4000]
    return "es" if len(ESPANOL.findall(limpio)) > len(INGLES.findall(limpio)) else "en"


def salario_mensual_usd(
    minimo, maximo, moneda: str | None, periodo: str | None
) -> tuple[float, float] | None:
    """El rango llevado a dólares al mes. None si la oferta no lo dice."""
    valores = [v for v in (minimo, maximo) if v]
    if not valores:
        return None
    tasa = USD_POR.get((moneda or "USD").upper())
    if tasa is None:
        return None
    periodo = (periodo or "mes").lower()
    if periodo.startswith(("year", "año", "anual", "annual", "ano")):
        factor = 1 / 12
    elif periodo.startswith(("hour", "hora")):
        factor = HORAS_AL_MES
    else:
        factor = 1
    bajo, alto = min(valores), max(valores)
    return round(bajo * tasa * factor), round(alto * tasa * factor)


def donde(ubicacion: str, remoto: bool | None, descripcion: str) -> str:
    """¿Puede trabajar desde Colombia? si | no | desconocido."""
    ubic = normalizar(ubicacion).strip()
    desc = normalizar(descripcion)
    if SOLO_ALLA.search(desc):
        return "no"
    if remoto is False:
        return "si" if re.search(r"colombia|bogota|bucaramanga|medellin|\bcali\b", ubic) else "no"
    if not ubic:
        return "desconocido"
    if GEO_OK.search(ubic):
        return "si"
    # Un remoto que nombra un país o región (y no Colombia ni LATAM) suele ser solo para
    # quien vive allá: «Costa Rica», «Turkey», «Remote, France».
    if GEO_RESTRINGIDA.search(ubic) or re.search(r"[a-z]{3,}", ubic):
        return "no"
    return "desconocido"


def evaluar(
    titulo: str,
    descripcion: str,
    ubicacion: str = "",
    remoto: bool | None = None,
    salario: tuple[float, float] | None = None,
    expectativa_usd_mes: float | None = None,
    anios_experiencia: float = 6.0,
    idioma: str | None = None,
    ciudad: str | None = None,
    domina: set[str] | None = None,
    lenguajes: set[str] | None = None,
) -> Analisis:
    """`ciudad`: donde vive (un presencial ahí no obliga a mudarse). `domina` y `lenguajes`:
    las tecnologías y lenguajes propios; por defecto los de vocabulario.py."""
    domina = domina or DOMINA
    lenguajes = lenguajes or LENGUAJES_SUYOS
    titulo_n = normalizar(titulo)
    texto = f"{titulo}\n{descripcion}"
    razones: list[str] = []

    # 1. Tecnologías (45)
    pide = tecnologias_en(texto)
    coinciden = sorted(pide & domina)
    parecidas = sorted(t for t in pide - domina if PARIENTES.get(t) in domina)
    faltan = sorted(pide - domina - set(parecidas))
    # Con menos de 4 tecnologías detectadas la oferta es vaga: no se infla el puntaje.
    tec = 45 * (len(coinciden) + 0.5 * len(parecidas)) / max(len(pide), 4)
    if coinciden:
        razones.append(
            f"Pide {len(coinciden)} {'cosa' if len(coinciden) == 1 else 'cosas'} que dominas: "
            f"{', '.join(nombre(t) for t in coinciden[:8])}."
        )
    if parecidas:
        razones.append(
            "Parecidas a lo tuyo: "
            + ", ".join(f"{nombre(t)} (tienes {nombre(PARIENTES[t])})" for t in parecidas)
            + "."
        )
    if faltan:
        razones.append(f"No tienes: {', '.join(nombre(t) for t in faltan)}.")

    # 2. Rol (25)
    if ROL_OTRO.search(titulo_n) and not re.search(r"full[- ]?stack", titulo_n):
        rol = 0
        razones.append("El rol no es de backend ni de integraciones.")
    elif ROL_FUERTE.search(titulo_n):
        rol = 25
        razones.append("El rol es justo lo tuyo (backend, full-stack, integraciones o IA).")
    elif ROL_GENERICO.search(titulo_n):
        rol = 16
    else:
        rol = 5

    # 3. Nivel (10)
    if NIVEL_BAJO.search(titulo_n):
        nivel = -12
        razones.append("Es para junior: te quedaría pequeño y pagaría poco.")
    elif NIVEL_ALTO.search(titulo_n):
        nivel = 4
        razones.append("Pide liderazgo o arquitectura: es un paso arriba, se puede intentar.")
    elif NIVEL_BUENO.search(titulo_n):
        nivel = 10
    else:
        nivel = 6

    # 4. Desde Colombia (20)
    puede = donde(ubicacion, remoto, descripcion)
    if puede == "si":
        lugar = 20
        if remoto is False:
            if ciudad and normalizar(ciudad) in normalizar(ubicacion):
                razones.append(f"Presencial o híbrido en {ubicacion}: en tu ciudad.")
            else:
                lugar = 8
                razones.append(f"Presencial o híbrido en {ubicacion}: tendrías que mudarte.")
    elif puede == "desconocido":
        lugar = 10
        razones.append("No dice desde qué países aceptan: confírmalo antes de aplicar.")
    else:
        lugar = -25
        razones.append(
            f"Parece solo para quien vive en {ubicacion or 'otro país'}: probablemente no aceptan Colombia."
        )

    puntaje = tec + rol + nivel + lugar

    # El lenguaje principal manda: si el título lo dice (.NET, Go, Ruby…), o si la oferta
    # solo pide lenguajes que no son los propios.
    ajenos = (pide & LENGUAJES_AJENOS) - lenguajes
    en_titulo = (tecnologias_en(titulo) & LENGUAJES_AJENOS) - lenguajes
    if en_titulo:
        ajenos = en_titulo
    if ajenos and (en_titulo or not pide & lenguajes):
        puntaje -= 20
        razones.append(
            f"El lenguaje principal es {', '.join(nombre(t) for t in sorted(ajenos))}, que no manejas."
        )

    # En contra
    anios = [int(n) for n in ANIOS.findall(normalizar(descripcion)) if 0 < int(n) <= 25]
    if anios and max(anios) > anios_experiencia + 2:
        puntaje -= 8
        razones.append(
            f"Pide {max(anios)} años de experiencia; tienes unos {anios_experiencia:.0f}."
        )
    if salario:
        razones.append(f"Paga entre US${salario[0]:,.0f} y US${salario[1]:,.0f} al mes.")
        if expectativa_usd_mes and salario[1] < expectativa_usd_mes:
            puntaje -= 10
            razones.append("Paga menos de lo que esperas.")

    # Qué logros van primero en la hoja de vida: lo que nombra el título pesa más, y
    # DevOps casi siempre es secundario (casi toda oferta menciona Docker o AWS).
    en_el_titulo = tecnologias_en(titulo)

    def peso(etiqueta: str) -> float:
        techs = ETIQUETA_DE[etiqueta]
        valor = len(pide & techs) + 3 * len(en_el_titulo & techs)
        return valor * 0.5 if etiqueta == "devops" else valor

    etiquetas = sorted(
        (e for e, techs in ETIQUETA_DE.items() if pide & techs), key=peso, reverse=True
    )
    if "backend" not in etiquetas:
        etiquetas.append("backend")

    return Analisis(
        puntaje=max(0, min(100, round(puntaje))),
        razones=razones,
        coinciden=[nombre(t) for t in coinciden],
        parecidas=[nombre(t) for t in parecidas],
        faltan=[nombre(t) for t in faltan],
        etiquetas_cv=etiquetas,
        idioma=idioma if idioma in ("es", "en") else idioma_de(texto),
        remoto_desde_colombia=puede,
        salario_usd_mes=salario,
    )
