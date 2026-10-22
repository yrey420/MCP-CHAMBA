"""Las tecnologías que se buscan en una oferta y cuáles domina quien busca empleo.

Cada tecnología tiene una expresión para reconocerla en el texto (sin tildes y
en minúsculas). `DOMINA` es el conjunto predeterminado (un perfil backend
Python/Java); cada perfil puede reemplazarlo con `vocabulario.domina` y
`vocabulario.lenguajes` (ver perfil/perfil.example.yaml). `PARIENTES` son las que
no se tienen pero se acercan (FastAPI si se sabe Django), y cuentan a medias.
"""

from __future__ import annotations

import re
import unicodedata

TECNOLOGIAS: dict[str, str] = {
    "python": r"\bpython\b",
    "django": r"\bdjango\b",
    "drf": r"django rest framework|\bdrf\b",
    "fastapi": r"\bfastapi\b",
    "flask": r"\bflask\b",
    "java": r"\bjava\b(?!\s*script)",
    "spring": r"\bspring(\s*boot)?\b",
    "kotlin": r"\bkotlin\b",
    "scala": r"\bscala\b",
    "node": r"\bnode(\.?js)?\b|\bnestjs\b|\bexpress\.?js\b",
    "typescript": r"\btypescript\b",
    "javascript": r"\bjavascript\b",
    "php": r"\bphp\b",
    "laravel": r"\blaravel\b",
    "symfony": r"\bsymfony\b",
    "go": r"\bgolang\b|\bgo (developer|engineer|backend|services)\b|(^|[\s(,;/])go([,;/)]|\s+(and|or|y|o)\b)",
    "ruby": r"\bruby\b|\brails\b",
    "dotnet": r"\.net\b|\bc#|\basp\.net\b",
    "rust": r"\brust\b",
    "elixir": r"\belixir\b",
    "react": r"\breact(\.?js)?\b",
    "angular": r"\bangular\b",
    "vue": r"\bvue(\.?js)?\b",
    "nextjs": r"\bnext\.?js\b",
    "rest": r"\brest(ful)?\b",
    "graphql": r"\bgraphql\b",
    "grpc": r"\bgrpc\b",
    "soap": r"\bsoap\b",
    "webhooks": r"\bwebhooks?\b",
    "oauth": r"\boauth\s*2?\b|\boidc\b|\bopenid\b",
    "microservicios": r"micro-?services?|microservicios",
    "postgresql": r"\bpostgres(ql)?\b",
    "mysql": r"\bmysql\b|\bmariadb\b",
    "mongodb": r"\bmongo(db)?\b",
    "redis": r"\bredis\b",
    "elasticsearch": r"\belastic(search)?\b|\bopensearch\b",
    "kafka": r"\bkafka\b",
    "colas": r"\brabbitmq\b|\bsqs\b|\bpub/?sub\b|message queues?|colas de mensajes",
    "celery": r"\bcelery\b",
    "sql": r"\bsql\b",
    "aws": r"\baws\b|amazon web services|\bec2\b|\blambda\b|\bs3\b",
    "gcp": r"\bgcp\b|google cloud",
    "azure": r"\bazure\b",
    "docker": r"\bdocker\b|contenedores|containers?\b",
    "kubernetes": r"\bkubernetes\b|\bk8s\b",
    "terraform": r"\bterraform\b|infrastructure as code|infraestructura como codigo",
    "cicd": r"\bci ?/ ?cd\b|github actions|gitlab ci|\bjenkins\b|continuous (integration|delivery|deployment)",
    "linux": r"\blinux\b|\bubuntu\b",
    "observabilidad": r"new relic|datadog|grafana|prometheus|observability|observabilidad|opentelemetry|\bsentry\b",
    "pruebas": r"\bpytest\b|\bjunit\b|\btdd\b|unit tests?|automated tests?|pruebas (unitarias|automatizadas)",
    "llm": r"\bllms?\b|large language models?|generative ai|\bgenai\b|ia generativa|\bopenai\b|\banthropic\b|\bclaude\b|\bgpt-?\d",
    "agentes": r"\bai agents?\b|agentic|agentes? de ia|\blanggraph\b|\bcrewai\b|\bautogen\b",
    "langchain": r"\blangchain\b|\bllamaindex\b",
    "rag": r"\brag\b|retrieval[- ]augmented",
    "vectores": r"vector (db|database|store|search)|\bpgvector\b|\bpinecone\b|\bweaviate\b|\bqdrant\b|\bembeddings?\b",
    "mcp": r"\bmcp\b|model context protocol",
    "multitenant": r"multi-?tenant|multi-?inquilino",
    "erp": r"\berp\b|\bsap\b|\bodoo\b|\bnetsuite\b|dynamics 365|oracle (ebs|fusion)",
    "m365": r"microsoft 365|\bm365\b|office 365|power automate|power apps|sharepoint|microsoft graph",
    "integraciones": r"\bintegrations?\b|integraciones|third[- ]party apis?|apis? de terceros|\bipaas\b|\bzapier\b|\bmulesoft\b",
    "seguridad": r"\bowasp\b|\bxss\b|\bcsp\b|pentest|\bsoc ?2\b|application security|seguridad de aplicaciones",
    "saas": r"\bsaas\b",
    "movil": r"\bios\b|\bandroid\b|\bswift\b|react native|\bflutter\b",
    "ml": r"machine learning|data scien|\bpytorch\b|\btensorflow\b|deep learning",
}

# Lo que se domina por defecto. El perfil lo puede cambiar (vocabulario.domina).
DOMINA = {
    "python", "django", "drf", "java", "spring", "node", "typescript", "javascript", "php",
    "laravel", "symfony", "react", "angular", "rest", "graphql", "grpc", "soap", "webhooks",
    "oauth", "postgresql", "mysql", "mongodb", "redis", "celery", "sql", "aws", "docker",
    "kubernetes", "cicd", "linux", "observabilidad", "pruebas", "llm", "agentes", "rag",
    "vectores", "mcp", "multitenant", "erp", "m365", "integraciones", "seguridad", "saas",
}  # fmt: skip

# No las tiene, pero tiene algo muy parecido: cuentan a medias.
PARIENTES = {
    "fastapi": "django",
    "flask": "django",
    "kotlin": "java",
    "dotnet": "java",
    "vue": "react",
    "nextjs": "react",
    "langchain": "agentes",
    "gcp": "aws",
    "azure": "aws",
    "terraform": "docker",
    "colas": "celery",
    "kafka": "celery",
    "microservicios": "rest",
}

# Lenguajes: si la oferta pide uno ajeno y ninguno de los propios, no encaja.
# El perfil puede cambiar los propios (vocabulario.lenguajes).
LENGUAJES_SUYOS = {"python", "java", "node", "php"}
LENGUAJES_AJENOS = {"go", "ruby", "dotnet", "scala", "elixir", "rust", "kotlin"}

# Qué etiquetas de logros del perfil conviene poner primero según la oferta.
ETIQUETA_DE = {
    "ia": {"llm", "agentes", "langchain", "rag", "vectores", "mcp"},
    "integraciones": {
        "integraciones",
        "rest",
        "graphql",
        "soap",
        "webhooks",
        "oauth",
        "m365",
        "grpc",
    },
    "erp": {"erp"},
    "devops": {
        "docker",
        "kubernetes",
        "cicd",
        "aws",
        "gcp",
        "azure",
        "terraform",
        "linux",
        "observabilidad",
    },
    "seguridad": {"seguridad", "oauth"},
    "datos": {"postgresql", "mysql", "mongodb", "sql", "redis", "elasticsearch"},
    "frontend": {"react", "angular", "vue", "typescript", "javascript", "nextjs"},
    "backend": {
        "python",
        "django",
        "drf",
        "java",
        "spring",
        "node",
        "php",
        "laravel",
        "fastapi",
        "flask",
    },
}

NOMBRES = {
    "drf": "Django REST Framework",
    "spring": "Spring Boot",
    "node": "Node.js",
    "dotnet": ".NET / C#",
    "cicd": "CI/CD",
    "m365": "Microsoft 365 / Power Automate",
    "multitenant": "multi-tenant",
    "pruebas": "pruebas automatizadas",
    "agentes": "agentes de IA",
    "vectores": "bases vectoriales",
    "movil": "desarrollo móvil",
    "ml": "machine learning",
    "colas": "colas de mensajes",
    "llm": "LLMs",
    "go": "Go",
}

_COMPILADAS = {clave: re.compile(patron) for clave, patron in TECNOLOGIAS.items()}


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, para buscar sin importar cómo esté escrito."""
    sin_tildes = unicodedata.normalize("NFKD", texto or "")
    return "".join(c for c in sin_tildes if not unicodedata.combining(c)).lower()


def tecnologias_en(texto: str) -> set[str]:
    limpio = normalizar(texto)
    return {clave for clave, patron in _COMPILADAS.items() if patron.search(limpio)}


def del_perfil(perfil: dict) -> tuple[set[str], set[str]]:
    """Las tecnologías que domina y sus lenguajes, según el perfil (o las predeterminadas).
    Solo cuentan claves de TECNOLOGIAS."""
    vocabulario = perfil.get("vocabulario") or {}
    domina = {t for t in vocabulario.get("domina") or [] if t in TECNOLOGIAS} or DOMINA
    lenguajes = {t for t in vocabulario.get("lenguajes") or [] if t in TECNOLOGIAS}
    return domina, lenguajes or LENGUAJES_SUYOS


def nombre(clave: str) -> str:
    return NOMBRES.get(clave, clave.capitalize() if len(clave) > 3 else clave.upper())
