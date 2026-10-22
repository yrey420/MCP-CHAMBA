"""Servidor MCP de búsqueda de empleo (MCP Chamba).

Se conecta a Claude Code por stdio:

    claude mcp add --scope user empleo -- uv run --directory /ruta/a/MCP-CHAMBA empleo-mcp

El envío de cada postulación lo hace la persona: aquí se busca, se califica, se
prepara la hoja de vida y la carta, y se lleva el seguimiento.
"""

from __future__ import annotations

import json
import re
import statistics
import unicodedata
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated

import httpx
import yaml
from mcp.server.mcpserver import MCPServer
from pydantic import Field

from empleo import ajuste, cv, fuentes, rutas, vocabulario
from empleo.base import ABIERTOS, ESTADOS, Base
from empleo.perfil import (
    anios_de_experiencia,
    cargar,
    ciudad_base,
    es_de_ejemplo,
    nombre_archivo,
    resumen_para_el_agente,
    salida_ultimo_empleo,
)
from empleo.rutas import EMPRESAS, POSTULACIONES

INSTRUCCIONES = """\
Herramientas para conseguir empleo en nombre de la persona cuyo perfil devuelve ver_perfil.
Flujo: buscar_ofertas → ver_oferta → generar_cv_para_oferta (+ guardar_carta) → la persona
envía la postulación → actualizar_postulacion. ver_postulaciones muestra el seguimiento.

Reglas:
- Nunca inventes experiencia, cifras, tecnologías ni empresas: todo sale de ver_perfil. Las
  herramientas rechazan textos con cifras que no están en el perfil.
- Respeta siempre reglas_para_el_asistente del perfil (por ejemplo, acuerdos de
  confidencialidad: no nombrar clientes de empleos anteriores).
- La persona envía cada postulación; tú preparas los documentos y le das el enlace.
- Escribe en el idioma de la oferta (campo idioma del análisis).
- Si preguntan por la salida de su último empleo, usa salida_ultimo_empleo del perfil y sus
  reglas: corto, neutral y mirando hacia adelante.
"""

BUSQUEDAS_DIARIAS = [
    "python django",
    "backend python",
    "java spring boot",
    "integrations",
    "ai agents python",
]


def _instrucciones() -> str:
    """Las instrucciones fijas más las reglas propias del perfil, si hay uno."""
    try:
        perfil = cargar()
    except (OSError, ValueError, yaml.YAMLError):
        return INSTRUCCIONES
    reglas = list(perfil.get("reglas_para_el_asistente") or [])
    salida = salida_ultimo_empleo(perfil)
    if isinstance(salida, dict):
        reglas += salida.get("reglas") or []
    extra = f"\nPerfil activo: {perfil.get('datos', {}).get('nombre', '¿?')}"
    if es_de_ejemplo():
        extra += (
            " (perfil FICTICIO de ejemplo: copia perfil/perfil.example.yaml a perfil/perfil.yaml)"
        )
    if reglas:
        extra += "\nReglas del perfil:\n" + "\n".join(f"- {r}" for r in reglas)
    return INSTRUCCIONES + extra + "\n"


servidor = MCPServer(name="empleo", instructions=_instrucciones())


# --- Apoyo ---------------------------------------------------------------------------------


def _perfil() -> dict:
    return cargar(rutas.PERFIL)


def _expectativa_usd(perfil: dict) -> float | None:
    rango = (perfil.get("objetivo", {}).get("salario", {}) or {}).get("expectativa_dicha_cop_mes")
    return rango[0] * ajuste.USD_POR["COP"] if rango else None


def _analizar(oferta: fuentes.Oferta, perfil: dict) -> ajuste.Analisis:
    salario = ajuste.salario_mensual_usd(
        oferta.salario_min, oferta.salario_max, oferta.moneda, oferta.periodo
    )
    domina, lenguajes = vocabulario.del_perfil(perfil)
    return ajuste.evaluar(
        titulo=oferta.titulo,
        descripcion=oferta.descripcion,
        ubicacion=oferta.ubicacion,
        remoto=oferta.remoto,
        salario=salario,
        expectativa_usd_mes=_expectativa_usd(perfil),
        anios_experiencia=anios_de_experiencia(perfil),
        idioma=oferta.idioma,
        ciudad=ciudad_base(perfil),
        domina=domina,
        lenguajes=lenguajes,
    )


def _al_dia(base: Base, perfil: dict) -> int:
    """Vuelve a calificar las ofertas guardadas si cambiaron las reglas (ajuste.VERSION)."""
    viejas = base.desactualizadas(ajuste.VERSION)
    for fila in viejas:
        oferta = fuentes.oferta_desde_dict(fila)
        base.guardar_oferta(oferta, _analizar(oferta, perfil))
    return len(viejas)


def _resumen(fila: dict, razones: int = 4) -> dict:
    analisis = json.loads(fila.get("analisis") or "{}")
    return {
        "id": fila["id"],
        "puntaje": fila["puntaje"],
        "titulo": fila["titulo"],
        "empresa": fila["empresa"],
        "ubicacion": fila["ubicacion"],
        "desde_colombia": analisis.get("remoto_desde_colombia"),
        "salario_usd_mes": analisis.get("salario_usd_mes"),
        "idioma": analisis.get("idioma"),
        "publicada": (fila.get("publicada") or "")[:10],
        "url": fila["url"],
        "razones": analisis.get("razones", [])[:razones],
        "faltan": analisis.get("faltan", []),
        "postulacion": fila.get("estado_postulacion"),
    }


def _empresas() -> list[dict]:
    if not EMPRESAS.exists():
        return []
    return (yaml.safe_load(EMPRESAS.read_text(encoding="utf-8")) or {}).get("empresas", []) or []


def _slug(texto: str, largo: int = 40) -> str:
    limpio = unicodedata.normalize("NFKD", texto)
    limpio = "".join(c for c in limpio if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", limpio).strip("-")[:largo].strip("-")


_NUMERO = re.compile(r"(\d[\d.,]*\d|\d)\s*([kK]\b)?")


def _numeros(texto: str) -> set[str]:
    """Las cifras de un texto, sin separadores: «50.000», «50,000» y «50K» son «50000»."""
    cifras = set()
    for numero, mil in _NUMERO.findall(texto):
        limpio = re.sub(r"[.,]", "", numero)
        cifras.add(limpio + ("000" if mil else ""))
    return cifras


def _cifras_inventadas(texto: str, perfil: dict) -> list[str]:
    """Cifras que no aparecen en ninguna parte del perfil (un logro inventado)."""
    del_perfil = _numeros(rutas.PERFIL.read_text(encoding="utf-8"))
    return sorted(n for n in _numeros(texto) if n not in del_perfil and len(n) > 1)


def _carpeta(fila: dict) -> str:
    postulacion = Base().postulacion(fila["id"])
    if postulacion and postulacion.get("carpeta"):
        return postulacion["carpeta"]
    nombre = f"{date.today().isoformat()}-{_slug(fila['empresa'], 25)}-{_slug(fila['titulo'], 35)}"
    return str(POSTULACIONES / nombre)


# --- Perfil ---------------------------------------------------------------------------------


@servidor.tool()
def ver_perfil() -> dict:
    """Todo lo que se sabe de la persona: experiencia con logros (español e inglés, con
    etiquetas), habilidades, proyectos, historias para entrevistas, cómo contar la salida
    de su último empleo, reglas que debes respetar y lo que busca. Úsalo antes de escribir
    cualquier texto sobre ella."""
    perfil = _perfil()
    datos = resumen_para_el_agente(perfil)
    datos["anios_de_experiencia"] = anios_de_experiencia(perfil)
    if es_de_ejemplo():
        datos["aviso"] = (
            "Este es el perfil FICTICIO de ejemplo. Copia perfil/perfil.example.yaml a "
            "perfil/perfil.yaml (o define EMPLEO_PERFIL) con tus datos reales."
        )
    return datos


# --- Ofertas ---------------------------------------------------------------------------------


@servidor.tool()
async def buscar_ofertas(
    consulta: Annotated[
        str,
        Field(description="Qué buscar, ej: 'python django', 'java spring boot', 'integrations'."),
    ],
    fuentes_a_usar: Annotated[
        list[str] | None,
        Field(
            description="getonbrd, remotive, remoteok, jobicy, himalayas, arbeitnow. Vacío: las predeterminadas."
        ),
    ] = None,
    solo_remoto: bool = False,
    minimo: Annotated[int, Field(ge=0, le=100, description="Puntaje mínimo de ajuste.")] = 45,
    limite: Annotated[int, Field(ge=1, le=50)] = 15,
    forzar: Annotated[
        bool,
        Field(description="Consultar aunque la fuente se haya consultado hace menos de 6 h."),
    ] = False,
) -> dict:
    """Busca ofertas en portales con API pública, las califica de 0 a 100 contra el perfil y
    devuelve las mejores con sus razones. También incluye los portales de las empresas que se
    siguen (seguir_empresa). Lo ya visto queda guardado: repetir la búsqueda no gasta consultas."""
    perfil = _perfil()
    base = Base()
    elegidas = [f for f in (fuentes_a_usar or fuentes.PREDETERMINADAS) if f in fuentes.POR_BUSQUEDA]
    pendientes = [f for f in elegidas if forzar or not base.consulta_reciente(f, consulta)]
    empresas = [
        e
        for e in _empresas()
        if forzar or not base.consulta_reciente(f"{e['ats']}:{e['slug']}", "*")
    ]
    estado = {
        f: "consultada hace menos de 6 h: uso lo guardado" for f in elegidas if f not in pendientes
    }

    nuevas = 0
    if pendientes or empresas:
        ofertas, traidas = await fuentes.buscar(consulta, pendientes, empresas)
        estado.update(traidas)
        for oferta in ofertas:
            repetida = base.misma_oferta(oferta.empresa, oferta.titulo)
            if repetida and repetida != oferta.id:
                continue  # la misma vacante en otra fuente
            if base.oferta(oferta.id) is None:
                nuevas += 1
            base.guardar_oferta(oferta, _analizar(oferta, perfil))
        for clave, resultado in traidas.items():
            if not resultado.startswith("error"):
                base.anotar_consulta(clave, "*" if ":" in clave else consulta)

    _al_dia(base, perfil)
    palabras = fuentes.terminos(consulta)
    resultados = []
    for fila in base.ofertas(dias=30, minimo=minimo):
        oferta = fuentes.oferta_desde_dict(fila)
        if not fuentes.coincide(oferta, palabras):
            continue
        if solo_remoto and oferta.remoto is False:
            continue
        resultados.append(_resumen(fila))
        if len(resultados) >= limite:
            break
    return {
        "consulta": consulta,
        "fuentes": estado,
        "nuevas": nuevas,
        "resultados": resultados,
        "nota": "Puntaje: tecnologías 45, rol 25, nivel 10, desde Colombia 20, menos lo que pesa en contra.",
    }


@servidor.tool()
def agregar_oferta(
    titulo: str,
    empresa: str,
    descripcion: Annotated[
        str,
        Field(
            description="El texto completo de la oferta, copiado de LinkedIn, Computrabajo, etc."
        ),
    ],
    url: str = "",
    ubicacion: str = "",
    remoto: bool | None = None,
    salario_min: float | None = None,
    salario_max: float | None = None,
    moneda: Annotated[str | None, Field(description="USD, COP, EUR…")] = None,
    periodo: Annotated[str | None, Field(description="mes, año u hora")] = None,
) -> dict:
    """Guarda y califica una oferta que no viene de las APIs (LinkedIn, Computrabajo,
    elempleo, un correo de un reclutador…)."""
    oferta = fuentes.Oferta(
        fuente="manual",
        id_externo=f"{_slug(empresa, 25)}-{_slug(titulo, 35)}",
        titulo=titulo,
        empresa=empresa,
        url=url,
        descripcion=descripcion,
        ubicacion=ubicacion,
        remoto=remoto,
        salario_min=salario_min,
        salario_max=salario_max,
        moneda=moneda,
        periodo=periodo,
    )
    base = Base()
    analisis = _analizar(oferta, _perfil())
    base.guardar_oferta(oferta, analisis)
    return {"id": oferta.id, **analisis.como_dict()}


@servidor.tool()
def ver_oferta(oferta_id: str) -> dict:
    """Detalle completo de una oferta: descripción, análisis de ajuste (qué coincide y qué
    falta) y su postulación con historial, si la hay."""
    base = Base()
    fila = base.oferta(oferta_id)
    if fila is None:
        raise ValueError(f"No conozco la oferta {oferta_id}.")
    return {
        **_resumen(fila, razones=20),
        "analisis": json.loads(fila["analisis"]),
        "descripcion": fila["descripcion"][:9000],
        "postulacion": base.postulacion(oferta_id),
        "historial": base.historial(oferta_id),
    }


@servidor.tool()
def listar_ofertas(
    minimo: Annotated[int, Field(ge=0, le=100)] = 55,
    limite: Annotated[int, Field(ge=1, le=100)] = 20,
    sin_postulacion: Annotated[
        bool, Field(description="Solo las que todavía no se han preparado ni enviado.")
    ] = True,
    dias: int = 30,
) -> dict:
    """Las mejores ofertas guardadas de los últimos días, de mayor a menor ajuste."""
    base = Base()
    _al_dia(base, _perfil())
    filas = [
        f
        for f in base.ofertas(dias=dias, minimo=minimo)
        if not (sin_postulacion and f.get("estado_postulacion"))
    ]
    return {
        "total": len(filas),
        "ofertas": [_resumen(f, razones=2) for f in filas[:limite]],
    }


@servidor.tool()
def descartar_oferta(oferta_id: str, motivo: str = "") -> dict:
    """No volver a mostrar esta oferta (no interesa, no aceptan Colombia, ya se cerró…)."""
    base = Base()
    if base.oferta(oferta_id) is None:
        raise ValueError(f"No conozco la oferta {oferta_id}.")
    base.descartar(oferta_id)
    if base.postulacion(oferta_id):
        base.cambiar_estado(oferta_id, "descartada", motivo)
    return {"id": oferta_id, "descartada": True}


# --- Documentos --------------------------------------------------------------------------------


@servidor.tool()
def generar_cv_para_oferta(
    oferta_id: str,
    idioma: Annotated[str | None, Field(description="es o en. Vacío: el de la oferta.")] = None,
    titular: Annotated[
        str | None,
        Field(
            description="Titular adaptado a la oferta, con hechos del perfil. Vacío: el del perfil."
        ),
    ] = None,
    resumen: Annotated[
        str | None,
        Field(
            description="Párrafo de perfil adaptado a la oferta (4-6 líneas), solo con hechos y cifras del perfil."
        ),
    ] = None,
) -> dict:
    """Genera la hoja de vida en PDF adaptada a la oferta: pone primero los logros que más se
    parecen a lo que pide y usa el titular y resumen dados. Rechaza cifras que no estén en el
    perfil. Deja la postulación en estado «preparada»."""
    base = Base()
    fila = base.oferta(oferta_id)
    if fila is None:
        raise ValueError(f"No conozco la oferta {oferta_id}.")
    perfil = _perfil()
    inventadas = _cifras_inventadas(f"{titular or ''} {resumen or ''}", perfil)
    if inventadas:
        raise ValueError(
            f"El titular o el resumen mencionan {', '.join(inventadas)}, que no está en el perfil. "
            "Usa solo cifras del perfil (ver_perfil)."
        )
    analisis = json.loads(fila["analisis"])
    idioma = idioma or analisis.get("idioma") or "en"
    carpeta = _carpeta(fila)
    destino = Path(carpeta)
    destino.mkdir(parents=True, exist_ok=True)
    pdf = destino / f"CV-{nombre_archivo(perfil)}-{idioma.upper()}.pdf"
    paginas = cv.generar(
        perfil,
        pdf,
        idioma=idioma,
        etiquetas=analisis.get("etiquetas_cv"),
        titular=titular,
        resumen=resumen,
    )
    (destino / "oferta.md").write_text(
        f"# {fila['titulo']} — {fila['empresa']}\n\n{fila['url']}\n\n"
        f"Ubicación: {fila['ubicacion']}\nPuntaje: {fila['puntaje']}\n\n{fila['descripcion']}\n",
        encoding="utf-8",
    )
    actual = base.postulacion(oferta_id)
    if actual is None or actual["estado"] == "guardada":
        base.cambiar_estado(oferta_id, "preparada", "Hoja de vida generada", carpeta=carpeta)
    return {
        "pdf": str(pdf),
        "paginas": paginas,
        "carpeta": carpeta,
        "idioma": idioma,
        "logros_priorizados": analisis.get("etiquetas_cv"),
        "postular_en": fila["url"],
        "aviso": "Quedó de más de 2 páginas: acorta el resumen."
        if paginas > 2
        else "Generada con el perfil FICTICIO de ejemplo."
        if es_de_ejemplo()
        else None,
    }


@servidor.tool()
def guardar_carta(
    oferta_id: str,
    texto: Annotated[
        str,
        Field(
            description="La carta completa, párrafos separados por una línea en blanco. Corta (3-4 párrafos), "
            "en el idioma de la oferta, con 1-2 logros del perfil que respondan a lo que piden."
        ),
    ],
    idioma: Annotated[str | None, Field(description="es o en. Vacío: el de la oferta.")] = None,
) -> dict:
    """Guarda la carta de presentación (Markdown y PDF) en la carpeta de la postulación.
    Rechaza cifras que no estén en el perfil."""
    base = Base()
    fila = base.oferta(oferta_id)
    if fila is None:
        raise ValueError(f"No conozco la oferta {oferta_id}.")
    perfil = _perfil()
    inventadas = _cifras_inventadas(texto, perfil)
    if inventadas:
        raise ValueError(
            f"La carta menciona {', '.join(inventadas)}, que no está en el perfil. Usa solo cifras del perfil."
        )
    idioma = idioma or json.loads(fila["analisis"]).get("idioma") or "en"
    destino = Path(_carpeta(fila))
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "carta.md").write_text(texto.strip() + "\n", encoding="utf-8")
    pdf = destino / f"Carta-{nombre_archivo(perfil)}-{idioma.upper()}.pdf"
    cv.generar_carta(perfil, pdf, texto, idioma)
    if base.postulacion(oferta_id) is None:
        base.cambiar_estado(oferta_id, "preparada", "Carta escrita", carpeta=str(destino))
    return {"pdf": str(pdf), "markdown": str(destino / "carta.md")}


# --- Seguimiento --------------------------------------------------------------------------------


@servidor.tool()
def actualizar_postulacion(
    oferta_id: str,
    estado: Annotated[str, Field(description=f"Uno de: {', '.join(ESTADOS)}")],
    nota: str = "",
    seguimiento_en_dias: Annotated[
        int | None,
        Field(
            description="En cuántos días hacer seguimiento. Por defecto 7 al postular y 3 tras una entrevista."
        ),
    ] = None,
) -> dict:
    """Cambia el estado de una postulación (postulada, entrevista, oferta, rechazada…) y
    programa el próximo seguimiento."""
    if seguimiento_en_dias is None:
        seguimiento_en_dias = {
            "postulada": 7,
            "entrevista": 3,
            "prueba_tecnica": 3,
            "oferta": 2,
        }.get(estado)
    proxima = (
        date.today() + timedelta(days=seguimiento_en_dias)
        if seguimiento_en_dias is not None
        else None
    )
    return Base().cambiar_estado(oferta_id, estado, nota, proxima)


@servidor.tool()
def ver_postulaciones(
    estado: Annotated[str | None, Field(description=f"Filtrar por: {', '.join(ESTADOS)}")] = None,
) -> dict:
    """El tablero de postulaciones: cuántas hay en cada estado, cuáles tienen el seguimiento
    vencido (hay que escribirle al reclutador) y la lista."""
    base = Base()
    todas = base.postulaciones()
    hoy = date.today().isoformat()
    vencidas = [
        p
        for p in todas
        if p["estado"] in ABIERTOS and p.get("proxima_accion") and p["proxima_accion"] <= hoy
    ]
    lista = [p for p in todas if estado is None or p["estado"] == estado]
    return {
        "por_estado": {
            e: sum(1 for p in todas if p["estado"] == e)
            for e in ESTADOS
            if any(p["estado"] == e for p in todas)
        },
        "seguimientos_vencidos": [
            {
                "id": p["oferta_id"],
                "empresa": p["empresa"],
                "titulo": p["titulo"],
                "estado": p["estado"],
                "desde": p["proxima_accion"],
            }
            for p in vencidas
        ],
        "postulaciones": [
            {
                "id": p["oferta_id"],
                "empresa": p["empresa"],
                "titulo": p["titulo"],
                "estado": p["estado"],
                "proxima_accion": p.get("proxima_accion"),
                "nota": p.get("nota"),
                "carpeta": p.get("carpeta"),
                "url": p["url"],
            }
            for p in lista
        ],
    }


@servidor.tool()
def preparar_entrevista(oferta_id: str) -> dict:
    """Todo para preparar una entrevista: la oferta, qué coincide y qué falta, las historias
    STAR del perfil, cómo contar la salida del último empleo y el rango salarial de ofertas
    parecidas.
    Con eso arma preguntas probables, respuestas y qué preguntar a la empresa."""
    base = Base()
    fila = base.oferta(oferta_id)
    if fila is None:
        raise ValueError(f"No conozco la oferta {oferta_id}.")
    perfil = _perfil()
    analisis = json.loads(fila["analisis"])
    consulta = " ".join(analisis.get("coinciden", [])[:3]) or fila["titulo"]
    return {
        "oferta": {
            **_resumen(fila, razones=20),
            "descripcion": fila["descripcion"][:7000],
        },
        "coinciden": analisis.get("coinciden"),
        "faltan": analisis.get("faltan"),
        "historias": perfil.get("historias", []),
        "salida_ultimo_empleo": salida_ultimo_empleo(perfil),
        "reglas_para_el_asistente": perfil.get("reglas_para_el_asistente", []),
        "salario_de_la_oferta_usd_mes": analisis.get("salario_usd_mes"),
        "mercado": rango_salarial(consulta=consulta),
        "pedir": (
            "Prepara: 8-10 preguntas probables (técnicas y de comportamiento) con respuestas "
            "basadas en las historias; cómo cubrir lo que falta con honestidad; 3-4 preguntas "
            "para hacerle a la empresa; y la cifra salarial a pedir, anclada arriba."
        ),
    }


@servidor.tool()
def rango_salarial(
    consulta: Annotated[
        str, Field(description="Filtrar por términos, ej: 'django'. Vacío: todas.")
    ] = "",
    minimo: Annotated[int, Field(ge=0, le=100, description="Puntaje mínimo de ajuste.")] = 40,
) -> dict:
    """Cuánto pagan las ofertas guardadas que dicen salario, llevado a dólares al mes (y a
    pesos), comparado con lo que espera la persona (objetivo.salario del perfil)."""
    palabras = fuentes.terminos(consulta)
    puntos = []
    for fila in Base().ofertas(dias=90, minimo=minimo, incluir_descartadas=True):
        salario = json.loads(fila["analisis"]).get("salario_usd_mes")
        if not salario or not fuentes.coincide(fuentes.oferta_desde_dict(fila), palabras):
            continue
        medio = (salario[0] + salario[1]) / 2
        if 300 <= medio <= 40000:  # descarta datos absurdos
            puntos.append(medio)
    perfil = _perfil()
    esperado = _expectativa_usd(perfil)
    if len(puntos) < 3:
        return {
            "ofertas_con_salario": len(puntos),
            "nota": "Muy pocas ofertas con salario: busca más primero.",
        }
    cuartiles = statistics.quantiles(puntos, n=4)
    cop = 1 / ajuste.USD_POR["COP"]
    return {
        "ofertas_con_salario": len(puntos),
        "usd_mes": {
            "minimo": round(min(puntos)),
            "p25": round(cuartiles[0]),
            "mediana": round(cuartiles[1]),
            "p75": round(cuartiles[2]),
            "maximo": round(max(puntos)),
        },
        "cop_mes_mediana": round(cuartiles[1] * cop, -5),
        "tu_expectativa_usd_mes": round(esperado) if esperado else None,
        "nota": "Mayoría de ofertas remotas internacionales; las de Colombia suelen pagar menos.",
    }


@servidor.tool()
async def seguir_empresa(
    nombre: str,
    ats: Annotated[str, Field(description="greenhouse, lever o ashby")],
    slug: Annotated[
        str,
        Field(
            description="El identificador del portal: boards.greenhouse.io/<slug>, jobs.lever.co/<slug>, jobs.ashbyhq.com/<slug>"
        ),
    ],
) -> dict:
    """Agrega el portal de empleo de una empresa para revisarlo en cada búsqueda. Comprueba
    que exista antes de guardarlo."""
    if ats not in fuentes.POR_EMPRESA:
        raise ValueError("ats debe ser greenhouse, lever o ashby.")
    async with fuentes.cliente_http() as cliente:
        try:
            ofertas = await fuentes.POR_EMPRESA[ats](cliente, slug, nombre)
        except httpx.HTTPError as exc:
            raise ValueError(f"No encontré el portal {ats}/{slug}: {exc}") from exc
    empresas = _empresas()
    if not any(e["ats"] == ats and e["slug"] == slug for e in empresas):
        empresas.append({"nombre": nombre, "ats": ats, "slug": slug})
        EMPRESAS.parent.mkdir(parents=True, exist_ok=True)
        EMPRESAS.write_text(
            "# Portales de empresas que se revisan en cada búsqueda (seguir_empresa).\n"
            + yaml.safe_dump({"empresas": empresas}, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    return {
        "empresa": nombre,
        "ofertas_publicadas": len(ofertas),
        "siguiendo": len(empresas),
    }


# --- Guías (aparecen como comandos en Claude Code) -------------------------------------------------


@servidor.prompt()
def rutina_diaria() -> str:
    """La búsqueda del día: seguimientos, ofertas nuevas y qué preparar."""
    busquedas = (_perfil().get("objetivo") or {}).get("busquedas") or BUSQUEDAS_DIARIAS
    return (
        "Haz mi rutina de búsqueda de empleo:\n"
        "1. ver_postulaciones: dime qué seguimientos están vencidos y redacta un mensaje corto "
        "para cada reclutador.\n"
        "2. buscar_ofertas con estas búsquedas, una por una: "
        + ", ".join(f"'{b}'" for b in busquedas)
        + ".\n"
        "3. Muéstrame el top 10 combinado (sin repetidas), con puntaje, empresa, si aceptan "
        "Colombia, salario si lo dice y la razón principal. Marca las que ya tienen postulación.\n"
        "4. Pregúntame cuáles preparo. Para cada una sigue la guía 'postular'."
    )


@servidor.prompt()
def postular(oferta_id: str) -> str:
    """Prepara una postulación completa para una oferta."""
    return (
        f"Prepara mi postulación a la oferta {oferta_id}:\n"
        "1. ver_oferta y ver_perfil.\n"
        "2. Escribe un titular y un resumen de perfil adaptados a lo que pide la oferta, en su "
        "idioma, solo con hechos y cifras del perfil, y llama generar_cv_para_oferta.\n"
        "3. Escribe una carta corta (3-4 párrafos, sin clichés): por qué esta empresa, 1-2 logros "
        "medibles que respondan a lo que piden y cierre con la disponibilidad del perfil. Llama "
        "guardar_carta.\n"
        "4. Dime qué me falta según la oferta y cómo responderlo con honestidad si lo preguntan.\n"
        "5. Dame la ruta de los PDF y el enlace para postular. Cuando te confirme que envié, "
        "llama actualizar_postulacion con estado 'postulada'."
    )


def main() -> None:
    servidor.run("stdio")


if __name__ == "__main__":
    main()
