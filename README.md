# MCP Chamba

[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB.svg)](https://www.python.org/)
[![MCP](https://img.shields.io/badge/MCP-servidor%20stdio-6E56CF.svg)](https://modelcontextprotocol.io/)
[![Licencia: MIT](https://img.shields.io/badge/licencia-MIT-green.svg)](LICENSE)

> **English summary.** MCP Chamba is a local [Model Context Protocol](https://modelcontextprotocol.io/)
> server that turns Claude (Claude Code or Claude Desktop) into a job-search assistant. It pulls
> openings from public job-board APIs (Get on Board, Remotive, RemoteOK, Jobicy, Himalayas,
> Arbeitnow) and company boards (Greenhouse, Lever, Ashby), scores each one 0–100 against *your*
> profile with explainable reasons, generates an ATS-friendly CV and cover letter tailored to the
> offer (PDF), refuses any figure that is not in your profile, and tracks every application and
> follow-up in a local SQLite database. Your data never leaves your machine. The code and docs are
> in Spanish; it is tuned for candidates in Colombia / LATAM looking for remote work.

*Chamba* es "trabajo" en buena parte de Latinoamérica. Este servidor MCP le da a Claude las
herramientas para ayudarte a conseguirla: **buscar → calificar → adaptar la hoja de vida y la
carta → postularte tú → hacer seguimiento**.

---

## Contenido

- [Qué hace](#qué-hace)
- [Herramientas](#herramientas)
- [Arquitectura](#arquitectura)
- [Requisitos](#requisitos)
- [Instalación](#instalación)
- [Configuración](#configuración)
- [Conectarlo a Claude](#conectarlo-a-claude)
- [Uso: el flujo típico](#uso-el-flujo-típico)
- [Cómo se califica una oferta](#cómo-se-califica-una-oferta)
- [Privacidad](#privacidad)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Desarrollo y contribuciones](#desarrollo-y-contribuciones)
- [Limitaciones conocidas](#limitaciones-conocidas)
- [Licencia](#licencia)

## Qué hace

- **Busca ofertas** en portales con API pública y en los portales de empleo de las empresas que
  sigues, en paralelo, y guarda lo visto para no repetir consultas (cada fuente se consulta como
  máximo cada 6 horas por búsqueda).
- **Califica cada oferta de 0 a 100** contra tu perfil y explica por qué: qué tecnologías
  coinciden, cuáles se parecen a las tuyas, qué te falta, si aceptan gente desde Colombia, si
  pide más años de los que tienes o si paga menos de lo que esperas.
- **Genera la hoja de vida en PDF adaptada a la oferta**: una columna, texto real y sin tablas
  (la leen bien los filtros ATS), con primero los logros que más se parecen a lo que piden, en
  español o inglés según el idioma de la oferta.
- **Guarda la carta de presentación** (Markdown + PDF con el mismo encabezado de la hoja de vida).
- **No deja inventar**: si el titular, el resumen o la carta mencionan una cifra que no aparece en
  tu perfil (`250.000 usuarios`, `95 %`…), la herramienta lo rechaza.
- **Lleva el seguimiento** de cada postulación (guardada → preparada → postulada → entrevista →
  prueba técnica → oferta → aceptada / rechazada / descartada) y te avisa cuándo toca escribirle
  al reclutador.
- **Prepara entrevistas** con tus historias STAR, lo que coincide y lo que falta, y el rango
  salarial de ofertas parecidas.
- **Tú envías cada postulación.** El servidor nunca postula por ti: prepara los documentos y te
  da el enlace.

## Herramientas

| Herramienta | Qué hace |
| --- | --- |
| `ver_perfil` | Devuelve tu perfil (experiencia, logros bilingües con etiquetas, habilidades, proyectos, historias STAR, reglas para el asistente). Claude lo consulta antes de escribir cualquier cosa sobre ti. |
| `buscar_ofertas` | Busca en las fuentes elegidas y en las empresas seguidas, califica y devuelve las mejores con sus razones. |
| `listar_ofertas` | Las mejores ofertas guardadas de los últimos días, de mayor a menor ajuste. |
| `ver_oferta` | Detalle completo: descripción, análisis de ajuste y la postulación con su historial. |
| `agregar_oferta` | Guarda y califica una oferta pegada a mano (LinkedIn, Computrabajo, elempleo, un correo de un reclutador…). |
| `descartar_oferta` | No volver a mostrar una oferta (no interesa, no aceptan tu país, ya cerró…). |
| `generar_cv_para_oferta` | Genera la hoja de vida en PDF adaptada a la oferta y deja la postulación en estado `preparada`. |
| `guardar_carta` | Guarda la carta de presentación (Markdown y PDF) en la carpeta de la postulación. |
| `actualizar_postulacion` | Cambia el estado de una postulación y programa el próximo seguimiento (7 días al postular, 3 tras una entrevista). |
| `ver_postulaciones` | Tablero: cuántas hay por estado, qué seguimientos están vencidos y la lista completa. |
| `preparar_entrevista` | Reúne la oferta, coincidencias, faltantes, historias STAR, cómo contar tu salida del último empleo y el mercado salarial. |
| `rango_salarial` | Mínimo, cuartiles y máximo de lo que pagan las ofertas guardadas (USD/mes y COP/mes), comparado con tu expectativa. |
| `seguir_empresa` | Agrega el portal Greenhouse, Lever o Ashby de una empresa para revisarlo en cada búsqueda (comprueba que exista). |

Además expone dos **guías (prompts MCP)**, que en Claude Code aparecen al escribir `/`:

- `rutina_diaria`: seguimientos vencidos, búsquedas del día (las de `objetivo.busquedas` en tu
  perfil) y un top 10 para decidir qué preparar.
- `postular`: prepara una postulación completa (hoja de vida, carta, qué te falta y el enlace).

## Arquitectura

```text
            Claude Code / Claude Desktop
                       │  MCP por stdio
                       ▼
 ┌──────────────────── empleo/servidor.py ─────────────────────┐
 │ 13 herramientas + 2 guías · reglas anti-invención de cifras │
 └──┬──────────────┬───────────────┬──────────────┬────────────┘
    │              │               │              │
    ▼              ▼               ▼              ▼
 fuentes.py     ajuste.py       cv.py          base.py
 APIs públicas  puntaje 0-100   Jinja2 +       SQLite local
 de empleo      y razones       WeasyPrint     (ofertas, postulaciones,
 (httpx async)  (vocabulario)   → PDF          historial, consultas)
    │              │               │
    │              ▼               ▼
    │          perfil.py ◀── perfil/perfil.yaml (tuyo, fuera de git)
    ▼
 Get on Board · Remotive · RemoteOK · Jobicy · Himalayas · Arbeitnow
 Greenhouse · Lever · Ashby (portales de empresas)
```

| Módulo | Responsabilidad |
| --- | --- |
| `empleo/servidor.py` | Define el servidor MCP (`mcp` SDK, transporte stdio), las herramientas, las guías y las instrucciones para el modelo. |
| `empleo/fuentes.py` | Un conector por portal; todos devuelven `Oferta` normalizada (texto limpio de HTML, salario, moneda, periodo, remoto, fecha). |
| `empleo/ajuste.py` | Calcula el puntaje, las razones y qué etiquetas de logros van primero en la hoja de vida. |
| `empleo/vocabulario.py` | Diccionario de tecnologías (expresiones regulares), cuáles dominas y cuáles se parecen. |
| `empleo/perfil.py` | Carga el perfil y lo resume para el asistente (solo hechos del perfil). |
| `empleo/cv.py` + `plantillas/` | Arma la hoja de vida y la carta en HTML y las convierte a PDF. |
| `empleo/base.py` | Persistencia en SQLite y máquina de estados de las postulaciones. |
| `empleo/rutas.py` | Rutas de archivos, configurables con variables de entorno. |

Claude escribe los textos (titular, resumen, carta); el servidor aporta los hechos, valida las
cifras y produce los documentos. No hace falta ninguna clave de API.

## Requisitos

- **Python 3.12+** y **[uv](https://docs.astral.sh/uv/)** (gestiona el entorno y las dependencias).
- **Pango**, que WeasyPrint necesita para generar los PDF:
  - Debian / Ubuntu: `sudo apt install libpango-1.0-0 libpangoft2-1.0-0`
  - Fedora: `sudo dnf install pango`
  - Arch: `sudo pacman -S pango`
  - macOS: `brew install pango`
  - Windows: ver la [guía de WeasyPrint](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html).
- Recomendado: la fuente **Noto Sans** (`fonts-noto` / `noto-fonts`), que usa la plantilla.
- Claude Code o Claude Desktop.

## Instalación

```bash
git clone https://github.com/yrey420/MCP-CHAMBA.git
cd MCP-CHAMBA
uv sync                 # crea .venv e instala dependencias
uv run pytest           # opcional: 39 pruebas, sin salir a internet
```

## Configuración

### 1. Tu perfil

Todo lo que el asistente sabe de ti sale de un único archivo YAML. Parte del ejemplo (un perfil
**ficticio**, "Alex Ejemplo"):

```bash
cp perfil/perfil.example.yaml perfil/perfil.yaml
```

y edítalo con tus datos. `perfil/perfil.yaml` está en `.gitignore`: nunca se sube. Si no existe,
el servidor arranca con el perfil de ejemplo y lo avisa en `ver_perfil` y al generar documentos.

Secciones principales (el ejemplo trae comentarios en cada una):

| Sección | Para qué sirve |
| --- | --- |
| `datos` | Nombre, ciudad, teléfono, correo, LinkedIn, GitHub, idiomas. Van en el encabezado de la hoja de vida y la carta; `nombre_corto` nombra los PDF (`CV-Alex-Ejemplo-EN.pdf`). |
| `objetivo` | Roles, modalidades, disponibilidad, `salario.expectativa_dicha_cop_mes` (para marcar ofertas que pagan menos), `busquedas` de la rutina diaria y `ciudad` (opcional). |
| `vocabulario` | Opcional: `domina` y `lenguajes` (claves de `empleo/vocabulario.py`) si tu stack no es backend Python/Java. |
| `titular`, `resumen` | Versiones generales en español (`es`) e inglés (`en`). |
| `habilidades` | Grupos de habilidades para la hoja de vida. |
| `experiencia` | Empleos con `logros`; cada logro en `es`/`en` y con `etiquetas` (`backend`, `integraciones`, `ia`, `erp`, `devops`, `seguridad`, `datos`, `frontend`, `liderazgo`) para ordenarlos según la oferta. |
| `proyectos` | Proyectos propios; `incluir: false` los deja fuera de la hoja de vida. |
| `educacion`, `historias` | Estudios e historias STAR para entrevistas. |
| `salida_ultimo_empleo` | Cómo contar por qué saliste de tu último empleo, con sus `reglas`. |
| `reglas_para_el_asistente` | Reglas que Claude debe respetar siempre (p. ej. no nombrar clientes protegidos por un acuerdo de confidencialidad). Se agregan a las instrucciones del servidor. |
| `decisiones` | Notas y decisiones tuyas que el asistente debe conocer. |

### 2. Empresas que sigues (opcional)

No hace falta crearlo: `seguir_empresa` escribe `perfil/empresas.yaml` (también ignorado por
git). El formato está en `perfil/empresas.example.yaml`.

### 3. Variables de entorno (opcionales)

Por defecto todo vive dentro de la carpeta del proyecto. Puedes guardar tus datos en otro lugar:

| Variable | Por defecto | Contenido |
| --- | --- | --- |
| `EMPLEO_PERFIL` | `perfil/perfil.yaml` | Tu perfil maestro. |
| `EMPLEO_EMPRESAS` | `perfil/empresas.yaml` | Portales de empresas seguidas. |
| `EMPLEO_SALIDA` | `salida/` | Hojas de vida generales y una carpeta por postulación (`salida/postulaciones/AAAA-MM-DD-empresa-cargo/`). |
| `EMPLEO_BASE` | `datos/empleo.db` | Base SQLite de ofertas, postulaciones e historial. |

No se necesitan claves ni tokens: todas las fuentes son públicas.

## Conectarlo a Claude

### Claude Code

```bash
claude mcp add --scope user empleo -- uv run --directory /ruta/absoluta/a/MCP-CHAMBA empleo-mcp
```

Con tus datos fuera del repositorio:

```bash
claude mcp add --scope user empleo \
  -e EMPLEO_PERFIL="$HOME/.config/chamba/perfil.yaml" \
  -e EMPLEO_BASE="$HOME/.local/share/chamba/empleo.db" \
  -e EMPLEO_SALIDA="$HOME/Documentos/chamba" \
  -- uv run --directory /ruta/absoluta/a/MCP-CHAMBA empleo-mcp
```

Comprueba que quedó conectado con `claude mcp list` (o `/mcp` dentro de Claude Code).

### Claude Desktop

Edita `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`, Windows:
`%APPDATA%\Claude\`, Linux: `~/.config/Claude/`) y reinicia la aplicación:

```json
{
  "mcpServers": {
    "empleo": {
      "command": "uv",
      "args": ["run", "--directory", "/ruta/absoluta/a/MCP-CHAMBA", "empleo-mcp"],
      "env": {
        "EMPLEO_PERFIL": "/ruta/absoluta/a/perfil.yaml"
      }
    }
  }
}
```

Si Claude Desktop no encuentra `uv`, pon la ruta completa (`which uv`) en `command`.

> El ejecutable también se llama `mcp-chamba`; `empleo-mcp` y `mcp-chamba` son equivalentes.

## Uso: el flujo típico

Le hablas a Claude en lenguaje natural; él decide qué herramienta usar.

```text
buscar_ofertas ─▶ ver_oferta ─▶ generar_cv_para_oferta ─▶ (tú envías) ─▶ actualizar_postulacion
                                  + guardar_carta                         └─▶ ver_postulaciones
```

1. **Buscar.** *"Búscame ofertas de python django remotas"* → `buscar_ofertas` devuelve el top con
   puntaje, empresa, si aceptan Colombia, salario y razones.
2. **Revisar.** *"Muéstrame la de Acme"* → `ver_oferta` con lo que coincide y lo que falta.
3. **Preparar.** *"Prepárame la postulación"* (o la guía `/postular`) → Claude lee `ver_perfil`,
   escribe un titular y resumen adaptados solo con hechos de tu perfil, genera la hoja de vida con
   `generar_cv_para_oferta` y la carta con `guardar_carta`. Quedan en
   `salida/postulaciones/<fecha>-<empresa>-<cargo>/` junto con `oferta.md`.
4. **Postular (tú).** Abres el enlace, revisas los PDF y envías.
5. **Registrar.** *"Ya me postulé"* → `actualizar_postulacion` con estado `postulada`; el
   seguimiento queda programado para dentro de 7 días.
6. **Seguimiento.** *"¿Cómo voy?"* → `ver_postulaciones` muestra el tablero y los seguimientos
   vencidos; Claude puede redactar el mensaje al reclutador.
7. **Entrevista.** *"Prepárame la entrevista con Acme"* → `preparar_entrevista`: preguntas
   probables, respuestas con tus historias STAR, cómo cubrir lo que falta y qué cifra pedir.

Otros ejemplos:

- *"¿Cuánto están pagando por backend con Django?"* → `rango_salarial`
- *"Sigue el portal de Acme en Greenhouse, slug `acme`"* → `seguir_empresa`
- *"Te pego una oferta de LinkedIn, agrégala"* → `agregar_oferta`
- *"Esa no, descártala: solo aceptan gente en EE. UU."* → `descartar_oferta`

Sin Claude, también puedes generar la hoja de vida general:

```bash
uv run python generar_cv.py --idioma es
uv run python generar_cv.py --idioma en --etiquetas backend,integraciones,ia --salida salida/cv-ia.pdf
```

## Cómo se califica una oferta

El puntaje (0–100) suma cuatro partes y resta lo que pesa en contra. Lo importante son las
razones, que acompañan cada resultado:

| Parte | Peso | Cómo |
| --- | --- | --- |
| Tecnologías | 45 | Las que pide y dominas cuentan entero; las "parecidas" (FastAPI si sabes Django, Vue si sabes React…) cuentan a medias. Con menos de 4 tecnologías detectadas no se infla el puntaje. |
| Rol | 25 | Backend, full-stack, integraciones o IA puntúan alto; frontend, móvil, QA, ventas, etc., no. |
| Nivel | 10 | Senior / semi-senior suma; lead / staff es "un paso arriba"; junior resta. |
| Ubicación | 20 | Remoto que acepta Colombia / LATAM / mundial suma; "solo EE. UU.", W-2 o *security clearance* resta 25; presencial fuera de tu ciudad suma poco. |
| En contra | — | Lenguaje principal ajeno (Go, .NET, Ruby…) −20; muchos más años de experiencia de los que tienes −8; paga menos de tu expectativa −10. |

Al cambiar las reglas, sube `ajuste.VERSION`: las ofertas guardadas se vuelven a calificar solas.

## Privacidad

- **Todo es local.** Tu perfil, la base SQLite, las hojas de vida y las cartas viven en tu
  máquina. No hay telemetría ni servidores propios.
- **Lo único que sale a internet** son consultas de lectura a las APIs públicas de los portales
  (con el término de búsqueda), identificadas con un User-Agent propio y limitadas a una por
  fuente y búsqueda cada 6 horas.
- **Lo que ves en Claude** sí pasa por Claude: lo que devuelven las herramientas (incluido tu
  perfil) llega al modelo como cualquier otra conversación.
- **Nada personal entra en git**: `.gitignore` excluye `perfil/` (salvo los `*.example.yaml`),
  `datos/`, `salida/`, `*.db`, `*.pdf` y `.env`. Las pruebas usan el perfil ficticio y carpetas
  temporales.
- Usa `reglas_para_el_asistente` para lo que no debe decirse nunca (clientes bajo acuerdo de
  confidencialidad, temas personales, etc.).

## Estructura del proyecto

```text
MCP-CHAMBA/
├── empleo/
│   ├── servidor.py        # servidor MCP: herramientas, guías e instrucciones
│   ├── fuentes.py         # conectores a portales de empleo
│   ├── ajuste.py          # puntaje 0-100 y razones
│   ├── vocabulario.py     # tecnologías y cómo reconocerlas
│   ├── perfil.py          # carga y resumen del perfil
│   ├── cv.py              # hoja de vida y carta en PDF
│   ├── base.py            # SQLite: ofertas, postulaciones, historial
│   └── rutas.py           # rutas y variables de entorno
├── perfil/
│   ├── perfil.example.yaml    # perfil ficticio: cópialo a perfil.yaml
│   └── empresas.example.yaml  # formato de las empresas seguidas
├── plantillas/
│   ├── cv.html            # plantilla Jinja2 de la hoja de vida
│   ├── carta.html         # plantilla de la carta
│   └── cv.css             # estilos (una columna, apta para ATS)
├── tests/                 # pytest, sin red (httpx.MockTransport)
├── generar_cv.py          # CLI: hoja de vida general en PDF
├── pyproject.toml
├── uv.lock
└── LICENSE
```

Se crean al usarlo (y no se suben): `perfil/perfil.yaml`, `perfil/empresas.yaml`,
`datos/empleo.db` y `salida/`.

## Desarrollo y contribuciones

¡Bienvenidas! Issues y pull requests en español o inglés.

```bash
uv sync
uv run pytest            # pruebas
uv run ruff check .      # lint
uv run ruff format .     # formato
```

Pautas:

- **Nueva fuente de ofertas:** una función `async` en `empleo/fuentes.py` que reciba el cliente
  `httpx` y la consulta y devuelva `list[Oferta]`; regístrala en `POR_BUSQUEDA` (o en
  `POR_EMPRESA` si es un ATS por empresa) y agrega una prueba con una respuesta de ejemplo en
  `tests/test_fuentes.py`. Solo APIs públicas que permitan la consulta; nada de *scraping* que
  viole términos de uso.
- **Nueva tecnología:** agrégala a `TECNOLOGIAS` en `empleo/vocabulario.py` (y, si aplica, a
  `PARIENTES` o `ETIQUETA_DE`).
- **Cambios en el puntaje:** acompáñalos de pruebas en `tests/test_ajuste.py` y sube
  `ajuste.VERSION`.
- **Nunca** subas datos reales en pruebas, ejemplos o capturas: usa el perfil ficticio.

## Limitaciones conocidas

- Pensado para buscar **desde Colombia / LATAM**: las reglas de ubicación (`GEO_OK`,
  `GEO_RESTRINGIDA` en `empleo/ajuste.py`) y la conversión a pesos lo reflejan. Para otro país,
  ajusta esas expresiones.
- Las tasas de cambio (`ajuste.USD_POR`) son aproximadas y fijas: sirven para comparar rangos, no
  para cuentas exactas.
- LinkedIn, Computrabajo y elempleo no tienen API pública: esas ofertas se agregan pegando el
  texto (`agregar_oferta`).
- La detección de tecnologías es por expresiones regulares: puede tener falsos positivos o
  negativos en ofertas ambiguas.

## Licencia

[MIT](LICENSE) © 2026 Yeison Rey
