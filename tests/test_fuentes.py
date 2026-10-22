"""Los conectores con datos de ejemplo de cada API (sin salir a internet)."""

import asyncio
import json

import httpx

from empleo import fuentes

RESPUESTAS = {
    "getonbrd.com": {
        "data": [
            {
                "id": "backend-engineer-acme-remote-fbc2",
                "attributes": {
                    "title": "Back-end Software Engineer",
                    "description": "<p>Python &amp; Django</p><ul><li>REST APIs</li></ul>",
                    "functions": "<p>Build integrations</p>",
                    "remote": True,
                    "countries": ["Remote"],
                    "lang": "en",
                    "min_salary": 4000,
                    "max_salary": 6500,
                    "published_at": 1791378545,
                    "company": {"data": {"attributes": {"name": "Acme"}}},
                },
                "links": {
                    "public_url": "https://www.getonbrd.com/jobs/backend-engineer-acme-remote-fbc2"
                },
            }
        ]
    },
    "remoteok.com": [
        {"legal": "aviso"},
        {
            "id": "1137394",
            "position": "Senior Python Engineer",
            "company": "Globex",
            "description": "<p>Weâ\x80\x99re hiring</p>",
            "location": "Remote",
            "salary_min": 120000,
            "salary_max": 150000,
            "url": "https://remoteOK.com/remote-jobs/1137394",
            "date": "2026-09-15T00:00:26+00:00",
            "tags": ["python", "backend"],
        },
    ],
    "boards-api.greenhouse.io": {
        "jobs": [
            {
                "id": 1,
                "title": "Backend Engineer, Integrations",
                "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/1",
                "content": "&lt;p&gt;Django and &amp;amp; APIs&lt;/p&gt;",
                "location": {"name": "Remote, LATAM"},
                "first_published": "2026-10-01T00:00:00Z",
            },
            {
                "id": 2,
                "title": "Account Executive",
                "absolute_url": "https://job-boards.greenhouse.io/acme/jobs/2",
                "content": "Sales and some Python reports",
                "location": {"name": "Remote, LATAM"},
            },
        ]
    },
}


def _cliente() -> httpx.AsyncClient:
    def responder(request: httpx.Request) -> httpx.Response:
        for dominio, cuerpo in RESPUESTAS.items():
            if dominio in request.url.host:
                return httpx.Response(200, json=cuerpo)
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(responder))


def test_html_becomes_readable_text():
    assert (
        fuentes.a_texto("<p>Hola &amp; chao</p><ul><li>Uno</li><li>Dos</li></ul>")
        == "Hola & chao\n• Uno\n• Dos"
    )
    assert fuentes.a_texto("&lt;p&gt;Escapado&lt;/p&gt;") == "Escapado"
    assert fuentes.reparar("Weâ\x80\x99re") == "We’re"


def test_get_on_board_brings_company_salary_and_language():
    async def correr():
        async with _cliente() as cliente:
            return await fuentes.getonbrd(cliente, "django")

    [oferta] = asyncio.run(correr())

    assert oferta.empresa == "Acme"
    assert (oferta.salario_min, oferta.salario_max, oferta.moneda, oferta.periodo) == (
        4000,
        6500,
        "USD",
        "mes",
    )
    assert oferta.idioma == "en"
    assert "• REST APIs" in oferta.descripcion
    assert oferta.id == "getonbrd:backend-engineer-acme-remote-fbc2"


def test_remoteok_skips_the_legal_notice_and_fixes_the_text():
    async def correr():
        async with _cliente() as cliente:
            return await fuentes.remoteok(cliente, "python backend")

    [oferta] = asyncio.run(correr())

    assert oferta.descripcion == "We’re hiring"
    assert oferta.periodo == "año"


def test_company_boards_only_keep_matching_titles(monkeypatch):
    monkeypatch.setattr(fuentes, "cliente_http", _cliente)

    ofertas, estado = asyncio.run(
        fuentes.buscar(
            "python django backend",
            [],
            [{"nombre": "Acme", "ats": "greenhouse", "slug": "acme"}],
        )
    )

    assert [o.titulo for o in ofertas] == ["Backend Engineer, Integrations"]
    assert estado["greenhouse:acme"] == "1 de 2"


def test_a_failing_source_does_not_stop_the_others(monkeypatch):
    monkeypatch.setattr(fuentes, "cliente_http", _cliente)

    ofertas, estado = asyncio.run(fuentes.buscar("django", ["getonbrd", "jobicy"], []))

    assert len(ofertas) == 1
    assert estado["jobicy"].startswith("error")


def test_free_text_salaries():
    assert fuentes._salario_libre("$60k - $80k") == {
        "salario_min": 60000,
        "salario_max": 80000,
        "moneda": "USD",
        "periodo": "año",
    }
    assert fuentes._salario_libre("USD 4000-5000/month")["periodo"] == "mes"
    assert fuentes._salario_libre("Competitive") == {}


def test_saved_offer_comes_back_the_same():
    oferta = fuentes.Oferta("manual", "x", "Backend", "Acme", "u", remoto=True, etiquetas=["a"])
    fila = {
        **oferta.__dict__,
        "etiquetas": json.dumps(oferta.etiquetas),
        "remoto": 1,
        "puntaje": 50,
    }

    assert fuentes.oferta_desde_dict(fila) == oferta
