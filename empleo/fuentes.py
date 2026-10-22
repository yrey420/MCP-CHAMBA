"""De dónde salen las ofertas: APIs públicas de portales de empleo.

Solo fuentes que publican sus ofertas para que otros las consulten. LinkedIn,
Computrabajo y elempleo no tienen API: esas ofertas se agregan a mano
(herramienta agregar_oferta). Cada conector devuelve `Oferta` ya normalizada.

Buenas maneras: se identifica con un User-Agent propio, pide una sola página
por búsqueda y la base guarda cuándo se consultó cada fuente para no repetir
(ver base.consulta_reciente).
"""

from __future__ import annotations

import asyncio
import html
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

import httpx

from empleo.vocabulario import normalizar

USER_AGENT = "mcp-chamba/0.1 (busqueda personal de empleo; +https://github.com/yrey420/MCP-CHAMBA)"
TIMEOUT = 25


@dataclass
class Oferta:
    fuente: str
    id_externo: str
    titulo: str
    empresa: str
    url: str
    descripcion: str = ""
    ubicacion: str = ""
    remoto: bool | None = None
    salario_min: float | None = None
    salario_max: float | None = None
    moneda: str | None = None
    periodo: str | None = None  # mes | año | hora
    publicada: str | None = None  # ISO 8601
    idioma: str | None = None
    etiquetas: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"{self.fuente}:{self.id_externo}"


# --- Texto ----------------------------------------------------------------------------

_BLOQUES = re.compile(r"<\s*(br|/p|/li|/h\d|/div|/tr)\s*/?>", re.IGNORECASE)
_VINETAS = re.compile(r"<\s*li[^>]*>", re.IGNORECASE)
_ETIQUETAS = re.compile(r"<[^>]+>")


def a_texto(contenido: str | None) -> str:
    """HTML (a veces escapado dos veces) a texto plano legible."""
    if not contenido:
        return ""
    texto = reparar(html.unescape(contenido))
    if "&lt;" in texto or "&amp;" in texto:
        texto = html.unescape(texto)
    texto = _VINETAS.sub("\n• ", texto)
    texto = _BLOQUES.sub("\n", texto)
    texto = html.unescape(_ETIQUETAS.sub(" ", texto))
    lineas = [" ".join(linea.split()) for linea in texto.splitlines()]
    return "\n".join(linea for linea in lineas if linea).strip()


def reparar(texto: str) -> str:
    """Texto UTF-8 leído como latin-1 («weâ€™re» → «we're»)."""
    if not re.search(r"[ÂÃâ][\x80-\xbf€‚ƒ„…†‡ˆ‰Š‹ŒŽ‘’“”•–—˜™š›œžŸ]", texto):
        return texto
    for codificacion in ("latin-1", "cp1252"):
        try:
            return texto.encode(codificacion).decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return texto


def _iso(valor) -> str | None:
    if valor in (None, "", 0):
        return None
    if isinstance(valor, (int, float)):
        segundos = valor / 1000 if valor > 10**11 else valor
        return datetime.fromtimestamp(segundos, UTC).isoformat()
    return str(valor)


def _numero(valor) -> float | None:
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if numero > 0 else None


def coincide(oferta: Oferta, terminos: list[str], solo_titulo: bool = False) -> bool:
    """La oferta habla de lo que se busca (algún término en el título, las
    etiquetas o, si se permite, la descripción)."""
    if not terminos:
        return True
    donde = normalizar(" ".join([oferta.titulo, " ".join(oferta.etiquetas)]))
    if not solo_titulo:
        donde += " " + normalizar(oferta.descripcion)
    return any(re.search(rf"\b{re.escape(t)}\b", donde) for t in terminos)


def terminos(consulta: str) -> list[str]:
    return [t for t in normalizar(consulta).replace(",", " ").split() if len(t) >= 2]


# --- Conectores ------------------------------------------------------------------------


async def remotive(cliente: httpx.AsyncClient, consulta: str) -> list[Oferta]:
    """Remotive pide no consultar más de unas pocas veces al día: la base lo controla."""
    r = await cliente.get(
        "https://remotive.com/api/remote-jobs", params={"search": consulta, "limit": 50}
    )
    r.raise_for_status()
    return [
        Oferta(
            fuente="remotive",
            id_externo=str(j["id"]),
            titulo=j["title"],
            empresa=j.get("company_name", ""),
            url=j["url"],
            descripcion=a_texto(j.get("description")),
            ubicacion=j.get("candidate_required_location", ""),
            remoto=True,
            publicada=j.get("publication_date"),
            etiquetas=list(j.get("tags") or []),
            **_salario_libre(j.get("salary", "")),
        )
        for j in r.json().get("jobs", [])
    ]


async def getonbrd(cliente: httpx.AsyncClient, consulta: str) -> list[Oferta]:
    """Get on Board: fuerte en Latinoamérica; salarios en dólares al mes."""
    r = await cliente.get(
        "https://www.getonbrd.com/api/v0/search/jobs",
        params={"query": consulta, "per_page": 50, "expand": '["company"]'},
    )
    r.raise_for_status()
    ofertas = []
    for j in r.json().get("data", []):
        a = j["attributes"]
        empresa = (((a.get("company") or {}).get("data") or {}).get("attributes") or {}).get(
            "name", ""
        )
        paises = a.get("countries") or []
        partes = [
            a.get("description"),
            a.get("functions"),
            a.get("desirable"),
            a.get("benefits"),
        ]
        ofertas.append(
            Oferta(
                fuente="getonbrd",
                id_externo=j["id"],
                titulo=a["title"],
                empresa=empresa,
                url=(j.get("links") or {}).get(
                    "public_url", f"https://www.getonbrd.com/jobs/{j['id']}"
                ),
                descripcion=a_texto("\n".join(p for p in partes if p)),
                ubicacion=", ".join(paises),
                remoto=bool(a.get("remote")),
                salario_min=_numero(a.get("min_salary")),
                salario_max=_numero(a.get("max_salary")),
                moneda="USD",
                periodo="mes",
                publicada=_iso(a.get("published_at")),
                # Puede venir «lang_not_specified»: entonces se detecta por el texto.
                idioma=a.get("lang") if a.get("lang") in ("es", "en") else None,
            )
        )
    return ofertas


async def remoteok(cliente: httpx.AsyncClient, consulta: str) -> list[Oferta]:
    """RemoteOK filtra por una etiqueta: se usa la primera palabra de la búsqueda."""
    etiqueta = (terminos(consulta) or ["python"])[0]
    r = await cliente.get("https://remoteok.com/api", params={"tag": etiqueta})
    r.raise_for_status()
    return [
        Oferta(
            fuente="remoteok",
            id_externo=str(j["id"]),
            titulo=reparar(j.get("position", "")),
            empresa=reparar(j.get("company", "")),
            url=j.get("url") or j.get("apply_url", ""),
            descripcion=a_texto(j.get("description")),
            ubicacion=reparar(j.get("location", "")),
            remoto=True,
            salario_min=_numero(j.get("salary_min")),
            salario_max=_numero(j.get("salary_max")),
            moneda="USD",
            periodo="año",
            publicada=j.get("date"),
            etiquetas=list(j.get("tags") or []),
        )
        for j in r.json()
        if isinstance(j, dict) and j.get("id")  # el primero es el aviso legal
    ]


async def jobicy(cliente: httpx.AsyncClient, consulta: str) -> list[Oferta]:
    r = await cliente.get(
        "https://jobicy.com/api/v2/remote-jobs", params={"count": 50, "tag": consulta}
    )
    r.raise_for_status()
    return [
        Oferta(
            fuente="jobicy",
            id_externo=str(j["id"]),
            titulo=html.unescape(j.get("jobTitle", "")),
            empresa=html.unescape(j.get("companyName", "")),
            url=j["url"],
            descripcion=a_texto(j.get("jobDescription")),
            ubicacion=j.get("jobGeo", ""),
            remoto=True,
            salario_min=_numero(j.get("salaryMin")),
            salario_max=_numero(j.get("salaryMax")),
            moneda=j.get("salaryCurrency"),
            periodo=j.get("salaryPeriod"),
            publicada=j.get("pubDate"),
            etiquetas=list(j.get("jobIndustry") or []),
        )
        for j in r.json().get("jobs", [])
    ]


async def himalayas(cliente: httpx.AsyncClient, consulta: str) -> list[Oferta]:
    r = await cliente.get(
        "https://himalayas.app/jobs/api/search", params={"q": consulta, "limit": 20}
    )
    r.raise_for_status()
    ofertas = []
    for j in r.json().get("jobs", []):
        lugares = j.get("locationRestrictions") or []
        ofertas.append(
            Oferta(
                fuente="himalayas",
                id_externo=j.get("guid") or j.get("applicationLink", ""),
                titulo=j.get("title", ""),
                empresa=j.get("companyName", ""),
                url=j.get("applicationLink") or j.get("guid", ""),
                descripcion=a_texto(j.get("description")),
                ubicacion=", ".join(lugares) if lugares else "Worldwide",
                remoto=True,
                salario_min=_numero(j.get("minSalary")),
                salario_max=_numero(j.get("maxSalary")),
                moneda=j.get("currency"),
                periodo=j.get("salaryPeriod"),
                publicada=_iso(j.get("pubDate")),
                etiquetas=list(j.get("categories") or []),
            )
        )
    return ofertas


async def arbeitnow(cliente: httpx.AsyncClient, consulta: str) -> list[Oferta]:
    """Sobre todo Alemania y Europa: no viene por defecto en las búsquedas."""
    r = await cliente.get("https://www.arbeitnow.com/api/job-board-api")
    r.raise_for_status()
    return [
        Oferta(
            fuente="arbeitnow",
            id_externo=j["slug"],
            titulo=j["title"],
            empresa=j.get("company_name", ""),
            url=j["url"],
            descripcion=a_texto(j.get("description")),
            ubicacion=j.get("location", ""),
            remoto=bool(j.get("remote")),
            publicada=_iso(j.get("created_at")),
            etiquetas=list(j.get("tags") or []),
        )
        for j in r.json().get("data", [])
    ]


async def greenhouse(cliente: httpx.AsyncClient, slug: str, empresa: str) -> list[Oferta]:
    r = await cliente.get(
        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
        params={"content": "true"},
    )
    r.raise_for_status()
    return [
        Oferta(
            fuente="greenhouse",
            id_externo=f"{slug}-{j['id']}",
            titulo=j["title"],
            empresa=j.get("company_name") or empresa,
            url=j["absolute_url"],
            descripcion=a_texto(j.get("content")),
            ubicacion=(j.get("location") or {}).get("name", ""),
            remoto="remote" in normalizar((j.get("location") or {}).get("name", "")) or None,
            publicada=j.get("first_published") or j.get("updated_at"),
        )
        for j in r.json().get("jobs", [])
    ]


async def lever(cliente: httpx.AsyncClient, slug: str, empresa: str) -> list[Oferta]:
    r = await cliente.get(f"https://api.lever.co/v0/postings/{slug}", params={"mode": "json"})
    r.raise_for_status()
    ofertas = []
    for j in r.json():
        categorias = j.get("categories") or {}
        listas = "\n".join(
            f"{x.get('text', '')}\n{a_texto(x.get('content'))}" for x in j.get("lists") or []
        )
        rango = j.get("salaryRange") or {}
        intervalo = (rango.get("interval") or "").lower()
        ofertas.append(
            Oferta(
                fuente="lever",
                id_externo=f"{slug}-{j['id']}",
                titulo=j.get("text", ""),
                empresa=empresa,
                url=j.get("hostedUrl", ""),
                descripcion="\n".join(
                    p
                    for p in [
                        j.get("descriptionPlain"),
                        listas,
                        j.get("additionalPlain"),
                    ]
                    if p
                ),
                ubicacion=categorias.get("location", ""),
                remoto=(j.get("workplaceType") == "remote") or None,
                salario_min=_numero(rango.get("min")),
                salario_max=_numero(rango.get("max")),
                moneda=rango.get("currency"),
                periodo="año" if "year" in intervalo else "hora" if "hour" in intervalo else "mes",
                publicada=_iso(j.get("createdAt")),
            )
        )
    return ofertas


async def ashby(cliente: httpx.AsyncClient, slug: str, empresa: str) -> list[Oferta]:
    r = await cliente.get(
        f"https://api.ashbyhq.com/posting-api/job-board/{slug}",
        params={"includeCompensation": "true"},
    )
    r.raise_for_status()
    ofertas = []
    for j in r.json().get("jobs", []):
        if not j.get("isListed", True):
            continue
        lugares = [j.get("location", "")] + [
            x.get("location", "") for x in j.get("secondaryLocations") or []
        ]
        compensacion = ((j.get("compensation") or {}).get("compensationTierSummary")) or ""
        ofertas.append(
            Oferta(
                fuente="ashby",
                id_externo=f"{slug}-{j['id']}",
                titulo=j.get("title", "").strip(),
                empresa=empresa,
                url=j.get("jobUrl", ""),
                descripcion=(j.get("descriptionPlain") or a_texto(j.get("descriptionHtml")))
                + (f"\nCompensación: {compensacion}" if compensacion else ""),
                ubicacion=", ".join(x for x in lugares if x),
                remoto=bool(j.get("isRemote")),
                publicada=j.get("publishedAt"),
            )
        )
    return ofertas


def _salario_libre(texto: str) -> dict:
    """«$60k - $80k», «USD 4000-5000/month»… lo que se pueda entender."""
    if not texto:
        return {}
    limpio = texto.lower().replace(",", "")
    numeros = [
        float(n) * (1000 if k else 1) for n, k in re.findall(r"(\d+(?:\.\d+)?)\s*(k)?", limpio)
    ]
    numeros = [n for n in numeros if n >= 100]
    if not numeros:
        return {}
    moneda = "EUR" if "€" in texto or "eur" in limpio else "GBP" if "£" in texto else "USD"
    periodo = (
        "hora"
        if "hour" in limpio or "/h" in limpio
        else "mes"
        if "month" in limpio or "mes" in limpio
        else "año"
    )
    if max(numeros) >= 15000 and periodo == "mes":
        periodo = "año"
    return {
        "salario_min": min(numeros),
        "salario_max": max(numeros),
        "moneda": moneda,
        "periodo": periodo,
    }


# --- Todo junto ------------------------------------------------------------------------

POR_BUSQUEDA = {
    "getonbrd": getonbrd,
    "remotive": remotive,
    "remoteok": remoteok,
    "jobicy": jobicy,
    "himalayas": himalayas,
    "arbeitnow": arbeitnow,
}
POR_EMPRESA = {"greenhouse": greenhouse, "lever": lever, "ashby": ashby}
# Arbeitnow es casi todo presencial en Alemania: solo si se pide.
PREDETERMINADAS = ["getonbrd", "remotive", "remoteok", "jobicy", "himalayas"]


def cliente_http() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        follow_redirects=True,
    )


async def buscar(
    consulta: str, fuentes: list[str], empresas: list[dict]
) -> tuple[list[Oferta], dict[str, str]]:
    """Consulta las fuentes en paralelo. Devuelve las ofertas que hablan de lo
    que se busca y, por fuente, cuántas trajo o qué error dio."""
    palabras = terminos(consulta)
    tareas: dict[str, asyncio.Task] = {}
    async with cliente_http() as cliente:
        for nombre in fuentes:
            if nombre in POR_BUSQUEDA:
                tareas[nombre] = asyncio.create_task(POR_BUSQUEDA[nombre](cliente, consulta))
        for empresa in empresas:
            funcion = POR_EMPRESA.get(empresa.get("ats", ""))
            if funcion:
                clave = f"{empresa['ats']}:{empresa['slug']}"
                tareas[clave] = asyncio.create_task(
                    funcion(cliente, empresa["slug"], empresa["nombre"])
                )
        resultados = await asyncio.gather(*tareas.values(), return_exceptions=True)

    ofertas: list[Oferta] = []
    estado: dict[str, str] = {}
    for clave, resultado in zip(tareas, resultados, strict=True):
        if isinstance(resultado, Exception):
            estado[clave] = f"error: {type(resultado).__name__}: {str(resultado)[:120]}"
            continue
        # Los portales de empresas traen todos sus cargos: se exige el término en el título.
        solo_titulo = ":" in clave
        utiles = [o for o in resultado if coincide(o, palabras, solo_titulo=solo_titulo)]
        estado[clave] = f"{len(utiles)} de {len(resultado)}"
        ofertas.extend(utiles)
    return ofertas, estado


def oferta_desde_dict(fila: dict) -> Oferta:
    datos = dict(fila)
    datos["etiquetas"] = json.loads(datos.get("etiquetas") or "[]")
    remoto = datos.get("remoto")
    datos["remoto"] = None if remoto is None else bool(remoto)
    campos = Oferta.__dataclass_fields__
    return Oferta(**{k: v for k, v in datos.items() if k in campos})
