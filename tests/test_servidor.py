"""Las herramientas del MCP de punta a punta, con el perfil ficticio de ejemplo y una base y
carpetas temporales (nunca tocan tus datos reales)."""

import pytest

from empleo import rutas, servidor

OFERTA = (
    "Senior Backend Engineer for a multi-tenant SaaS. Python, Django, PostgreSQL, REST APIs and "
    "third-party integrations with OAuth2. Docker and AWS. Experience with LLM agents is a plus. "
    "Remote from LATAM."
)


@pytest.fixture(autouse=True)
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(rutas, "PERFIL", rutas.PERFIL_EJEMPLO)
    monkeypatch.setattr(rutas, "BASE", tmp_path / "empleo.db")
    monkeypatch.setattr(servidor, "POSTULACIONES", tmp_path / "postulaciones")
    monkeypatch.setattr(servidor, "EMPRESAS", tmp_path / "empresas.yaml")


def _agregar(**cambios):
    datos = {
        "titulo": "Senior Backend Engineer",
        "empresa": "Acme",
        "descripcion": OFERTA,
        "url": "https://acme.test/jobs/1",
        "ubicacion": "LATAM",
        "remoto": True,
    }
    return servidor.agregar_oferta(**(datos | cambios))


def test_a_pasted_offer_is_scored():
    resultado = _agregar()

    assert resultado["id"] == "manual:acme-senior-backend-engineer"
    assert resultado["puntaje"] >= 70
    assert resultado["idioma"] == "en"


def test_the_profile_has_what_the_assistant_needs():
    perfil = servidor.ver_perfil()

    assert perfil["nombre"].startswith("Alex")
    assert perfil["historias"]
    assert perfil["reglas_para_el_asistente"]
    assert perfil["salida_ultimo_empleo"]["es"]
    assert perfil["anios_de_experiencia"] > 5
    assert "FICTICIO" in perfil["aviso"]


def test_a_tailored_cv_is_generated_and_the_application_prepared(tmp_path):
    oferta = _agregar()

    resultado = servidor.generar_cv_para_oferta(
        oferta["id"],
        resumen="Backend engineer with 6+ years; brought 40+ endpoints from seconds to milliseconds.",
    )

    assert resultado["paginas"] <= 2
    assert resultado["idioma"] == "en"
    assert resultado["pdf"].endswith("CV-Alex-Ejemplo-EN.pdf")
    assert (tmp_path / "postulaciones").exists()
    assert servidor.ver_postulaciones()["por_estado"] == {"preparada": 1}


def test_an_invented_figure_is_rejected():
    oferta = _agregar()

    with pytest.raises(ValueError, match="250000"):
        servidor.generar_cv_para_oferta(oferta["id"], resumen="I served 250,000 users.")
    with pytest.raises(ValueError, match="95"):
        servidor.guardar_carta(oferta["id"], "I cut costs by 95%.")


def test_figures_written_other_ways_are_accepted():
    oferta = _agregar()

    resultado = servidor.guardar_carta(
        oferta["id"],
        "Hi,\n\nI worked on a platform with 20K daily users and 80+ customers.\n\nBest, Alex",
    )

    assert resultado["pdf"].endswith("Carta-Alex-Ejemplo-EN.pdf")


def test_follow_ups_come_due():
    oferta = _agregar()
    servidor.actualizar_postulacion(
        oferta["id"], "postulada", "Enviada por la web", seguimiento_en_dias=0
    )

    tablero = servidor.ver_postulaciones()

    assert tablero["por_estado"] == {"postulada": 1}
    assert tablero["seguimientos_vencidos"][0]["empresa"] == "Acme"


def test_an_unknown_state_is_refused():
    oferta = _agregar()

    with pytest.raises(ValueError, match="Estado desconocido"):
        servidor.actualizar_postulacion(oferta["id"], "contratado")


def test_discarded_offers_disappear_from_the_list():
    oferta = _agregar()
    servidor.descartar_oferta(oferta["id"], "No aceptan Colombia")

    assert servidor.listar_ofertas(minimo=0)["total"] == 0


def test_salary_range_needs_enough_data():
    _agregar(salario_min=4000, salario_max=5000, moneda="USD", periodo="mes")

    assert servidor.rango_salarial()["ofertas_con_salario"] == 1


def test_saved_offers_are_rescored_when_the_rules_change(monkeypatch):
    oferta = _agregar()
    monkeypatch.setattr(servidor.ajuste, "VERSION", 999)

    servidor.listar_ofertas(minimo=0)

    assert servidor.ver_oferta(oferta["id"])["analisis"]["version"] == 999


def test_the_daily_routine_uses_the_profile_searches():
    guia = servidor.rutina_diaria()

    assert "'python django'" in guia
    assert "'integrations'" in guia


def test_profile_rules_reach_the_instructions():
    instrucciones = servidor._instrucciones()

    assert "Alex Ejemplo" in instrucciones
    assert "clientes de Acme SaaS" in instrucciones
