"""Qué tan bien encaja una oferta con el perfil, de 0 a 100, y por qué.

El puntaje suma cuatro cosas: tecnologías (45), el rol (25), el nivel (10) y
si puede trabajar desde Colombia (20). Después resta lo que pesa en contra:
pedir muchos más años de experiencia o pagar menos de lo que se espera. Lo
importante no es el número sino las razones: con ellas se decide y se adapta
la hoja de vida.

Las reglas (qué habilidades se buscan, qué roles sirven, cómo pesa el nivel) son las
predeterminadas de un perfil backend (vocabulario.py), salvo que el perfil traiga su
sección `ajuste` (ver perfil/perfil.example.yaml): así sirve para cualquier oficio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace

from empleo import vocabulario
from empleo.vocabulario import normalizar

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


@dataclass(frozen=True)
class Nivel:
    patron: re.Pattern
    puntos: int
    texto: str = ""


@dataclass
class Reglas:
    """Contra qué se califica: lo que la persona sabe hacer y qué roles le sirven."""

    patrones: dict[str, re.Pattern]
    domina: set[str]
    parientes: dict[str, str]
    nombres: dict[str, str]
    etiqueta_de: dict[str, set[str]]
    etiqueta_base: str
    rol_fuerte: re.Pattern
    rol_generico: re.Pattern
    rol_otro: re.Pattern
    texto_rol_fuerte: str
    texto_rol_otro: str
    niveles: list[Nivel]  # el primero que coincide con el título manda
    nivel_otro: int
    rol_excepcion: re.Pattern | None = None  # títulos que no son «otro rol» aunque lo parezcan
    secundaria: str | None = None  # etiqueta que casi toda oferta menciona: pesa la mitad
    lenguajes_suyos: set[str] = field(default_factory=set)
    lenguajes_ajenos: set[str] = field(default_factory=set)
    texto_lenguaje: str = "El lenguaje principal es {}, que no manejas."

    def en(self, texto: str) -> set[str]:
        limpio = normalizar(texto)
        return {clave for clave, patron in self.patrones.items() if patron.search(limpio)}

    def nombre(self, clave: str) -> str:
        return self.nombres.get(clave, clave.capitalize() if len(clave) > 3 else clave.upper())


PREDETERMINADAS = Reglas(
    patrones={clave: re.compile(p) for clave, p in vocabulario.TECNOLOGIAS.items()},
    domina=vocabulario.DOMINA,
    parientes=vocabulario.PARIENTES,
    nombres=vocabulario.NOMBRES,
    etiqueta_de=vocabulario.ETIQUETA_DE,
    etiqueta_base="backend",
    rol_fuerte=ROL_FUERTE,
    rol_generico=ROL_GENERICO,
    rol_otro=ROL_OTRO,
    rol_excepcion=re.compile(r"full[- ]?stack"),
    texto_rol_fuerte="El rol es justo lo tuyo (backend, full-stack, integraciones o IA).",
    texto_rol_otro="El rol no es de backend ni de integraciones.",
    niveles=[
        Nivel(NIVEL_BAJO, -12, "Es para junior: te quedaría pequeño y pagaría poco."),
        Nivel(
            NIVEL_ALTO, 4, "Pide liderazgo o arquitectura: es un paso arriba, se puede intentar."
        ),
        Nivel(NIVEL_BUENO, 10),
    ],
    nivel_otro=6,
    secundaria="devops",
    lenguajes_suyos=vocabulario.LENGUAJES_SUYOS,
    lenguajes_ajenos=vocabulario.LENGUAJES_AJENOS,
)


def reglas_de(perfil: dict) -> Reglas:
    """Las reglas de la sección `ajuste` del perfil. Sin ella, las predeterminadas con las
    tecnologías y lenguajes de `vocabulario` del perfil, si los trae."""
    datos = perfil.get("ajuste")
    if not datos:
        domina, lenguajes = vocabulario.del_perfil(perfil)
        return replace(PREDETERMINADAS, domina=domina, lenguajes_suyos=lenguajes)
    habilidades = datos["habilidades"]
    idiomas = datos.get("idiomas", {})
    rol = datos["rol"]
    nivel = datos["nivel"]
    return Reglas(
        patrones={clave: re.compile(h["patron"]) for clave, h in habilidades.items()},
        domina={clave for clave, h in habilidades.items() if h.get("domina")},
        parientes={clave: h["pariente"] for clave, h in habilidades.items() if h.get("pariente")},
        nombres={clave: h["nombre"] for clave, h in habilidades.items() if h.get("nombre")},
        etiqueta_de={e: set(claves) for e, claves in datos["etiquetas"].items()},
        etiqueta_base=datos["etiqueta_base"],
        rol_fuerte=re.compile(rol["fuerte"]),
        rol_generico=re.compile(rol["generico"]),
        rol_otro=re.compile(rol["otro"]),
        rol_excepcion=re.compile(rol["excepcion"]) if rol.get("excepcion") else None,
        texto_rol_fuerte=rol["texto_fuerte"],
        texto_rol_otro=rol["texto_otro"],
        niveles=[
            Nivel(re.compile(n["patron"]), n["puntos"], n.get("texto", ""))
            for n in nivel["niveles"]
        ],
        nivel_otro=nivel["otro"],
        secundaria=datos.get("secundaria"),
        lenguajes_suyos=set(idiomas.get("suyos", [])),
        lenguajes_ajenos=set(idiomas.get("ajenos", [])),
        texto_lenguaje=idiomas.get("texto", Reglas.texto_lenguaje),
    )


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
    reglas: Reglas | None = None,
) -> Analisis:
    """`ciudad`: donde vive (un presencial ahí no obliga a mudarse). `reglas`: contra qué se
    califica (ver reglas_de); por defecto las predeterminadas. `domina` y `lenguajes`
    reemplazan las habilidades y lenguajes propios de esas reglas."""
    reglas = reglas or PREDETERMINADAS
    if domina or lenguajes:
        reglas = replace(
            reglas,
            domina=domina or reglas.domina,
            lenguajes_suyos=lenguajes or reglas.lenguajes_suyos,
        )
    nombre = reglas.nombre
    titulo_n = normalizar(titulo)
    texto = f"{titulo}\n{descripcion}"
    razones: list[str] = []

    # 1. Habilidades (45)
    pide = reglas.en(texto)
    coinciden = sorted(pide & reglas.domina)
    parecidas = sorted(t for t in pide - reglas.domina if reglas.parientes.get(t) in reglas.domina)
    faltan = sorted(pide - reglas.domina - set(parecidas))
    # Con menos de 4 habilidades detectadas la oferta es vaga: no se infla el puntaje.
    tec = 45 * (len(coinciden) + 0.5 * len(parecidas)) / max(len(pide), 4)
    if coinciden:
        razones.append(
            f"Pide {len(coinciden)} {'cosa' if len(coinciden) == 1 else 'cosas'} que dominas: "
            f"{', '.join(nombre(t) for t in coinciden[:8])}."
        )
    if parecidas:
        razones.append(
            "Parecidas a lo tuyo: "
            + ", ".join(f"{nombre(t)} (tienes {nombre(reglas.parientes[t])})" for t in parecidas)
            + "."
        )
    if faltan:
        razones.append(f"No tienes: {', '.join(nombre(t) for t in faltan)}.")

    # 2. Rol (25)
    excepcion = reglas.rol_excepcion and reglas.rol_excepcion.search(titulo_n)
    if reglas.rol_otro.search(titulo_n) and not excepcion:
        rol = 0
        razones.append(reglas.texto_rol_otro)
    elif reglas.rol_fuerte.search(titulo_n):
        rol = 25
        razones.append(reglas.texto_rol_fuerte)
    elif reglas.rol_generico.search(titulo_n):
        rol = 16
    else:
        rol = 5

    # 3. Nivel (10)
    nivel = reglas.nivel_otro
    for regla in reglas.niveles:
        if regla.patron.search(titulo_n):
            nivel = regla.puntos
            if regla.texto:
                razones.append(regla.texto)
            break

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
    suyos = reglas.lenguajes_suyos
    ajenos = (pide & reglas.lenguajes_ajenos) - suyos
    en_titulo = (reglas.en(titulo) & reglas.lenguajes_ajenos) - suyos
    if en_titulo:
        ajenos = en_titulo
    if ajenos and (en_titulo or not pide & suyos):
        puntaje -= 20
        razones.append(reglas.texto_lenguaje.format(", ".join(nombre(t) for t in sorted(ajenos))))

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

    # Qué logros van primero en la hoja de vida: lo que nombra el título pesa más, y la
    # etiqueta secundaria cuenta a medias (por defecto DevOps: casi toda oferta nombra Docker).
    en_el_titulo = reglas.en(titulo)

    def peso(etiqueta: str) -> float:
        techs = reglas.etiqueta_de[etiqueta]
        valor = len(pide & techs) + 3 * len(en_el_titulo & techs)
        return valor * 0.5 if etiqueta == reglas.secundaria else valor

    etiquetas = sorted(
        (e for e, techs in reglas.etiqueta_de.items() if pide & techs), key=peso, reverse=True
    )
    if reglas.etiqueta_base not in etiquetas:
        etiquetas.append(reglas.etiqueta_base)

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
