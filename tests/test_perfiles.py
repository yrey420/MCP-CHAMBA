"""Otra persona, otro oficio: sus reglas de ajuste salen de su perfil y sus archivos van
aparte (EMPLEO_PERSONA). El perfil es ficticio."""

import importlib

import pytest

from empleo import ajuste, rutas, vocabulario

# Alguien de atención al cliente y cumplimiento, no de software.
ATENCION = {
    "ajuste": {
        "habilidades": {
            "servicio": {
                "patron": r"customer (service|support|care)|atencion al cliente",
                "nombre": "servicio al cliente",
                "domina": True,
            },
            "disputas": {
                "patron": r"chargebacks?|disputes?|contracargos?",
                "nombre": "disputas y contracargos",
                "domina": True,
            },
            "cumplimiento": {
                "patron": r"compliance|\bkyc\b|cumplimiento",
                "nombre": "cumplimiento",
                "domina": True,
            },
            "procedimientos": {
                "patron": r"\bsops?\b|procedimientos",
                "nombre": "procedimientos",
                "domina": True,
            },
            "ingles": {"patron": r"\benglish\b|\bingles\b", "nombre": "inglés", "domina": True},
            "salesforce": {"patron": r"salesforce", "nombre": "Salesforce", "domina": True},
            "zendesk": {"patron": r"zendesk", "nombre": "Zendesk", "pariente": "salesforce"},
            "soporte_tecnico": {
                "patron": r"troubleshoot|technical support|soporte tecnico",
                "nombre": "soporte técnico",
            },
            "portugues": {"patron": r"portuguese|portugues", "nombre": "portugués"},
        },
        "idiomas": {
            "suyos": ["ingles"],
            "ajenos": ["portugues"],
            "texto": "Pide {}, un idioma que no manejas.",
        },
        "etiquetas": {
            "servicio": ["servicio", "salesforce", "zendesk"],
            "cumplimiento": ["disputas", "cumplimiento", "procedimientos"],
        },
        "etiqueta_base": "servicio",
        "rol": {
            "fuerte": r"specialist|analyst|agent|especialista|analista|asesor",
            "generico": r"assistant|associate|asistente|auxiliar",
            "otro": r"engineer|developer|ingenier|desarrollador",
            "texto_fuerte": "El rol es de oficina y servicio: lo tuyo.",
            "texto_otro": "El rol no es de oficina ni de servicio.",
        },
        "nivel": {
            "niveles": [
                {"patron": r"\bjunior\b|entry[- ]level", "puntos": 4, "texto": "Nivel inicial."},
                {"patron": r"\bsenior\b|\bsr\b", "puntos": 10},
            ],
            "otro": 10,
        },
    }
}
REGLAS = ajuste.reglas_de(ATENCION)


def _evaluar(titulo, descripcion, ubicacion="LATAM"):
    return ajuste.evaluar(
        titulo, descripcion, ubicacion, remoto=True, anios_experiencia=4.8, reglas=REGLAS
    )


def test_without_rules_in_the_profile_the_defaults_are_used():
    assert ajuste.reglas_de({}).domina == vocabulario.DOMINA
    assert ajuste.reglas_de({}).lenguajes_suyos == vocabulario.LENGUAJES_SUYOS

    go = ajuste.reglas_de({"vocabulario": {"domina": ["go"], "lenguajes": ["go"]}})

    assert go.domina == {"go"}
    assert go.lenguajes_suyos == {"go"}


def test_a_role_of_their_trade_scores_high():
    analisis = _evaluar(
        "Disputes & Chargebacks Specialist",
        "Fintech payments company. Review chargebacks and customer disputes, verify documents, "
        "follow SOPs and compliance policies. Excellent English. Salesforce or Zendesk.",
        "Worldwide",
    )

    assert analisis.puntaje >= 80
    assert "Salesforce" in analisis.coinciden
    assert "Zendesk" in analisis.parecidas
    assert analisis.etiquetas_cv[0] == "cumplimiento"


def test_an_engineering_role_does_not_fit_the_profile():
    analisis = _evaluar("Customer Support Engineer", "Troubleshoot APIs, technical support.")

    assert analisis.puntaje < 50
    assert "El rol no es de oficina" in " ".join(analisis.razones)


def test_a_language_outside_the_profile_weighs_against():
    analisis = _evaluar(
        "Bilingual Customer Support (Portuguese/English)",
        "Support Brazilian customers in Portuguese and English via chat.",
    )

    assert any("portugués" in r for r in analisis.razones)
    assert analisis.puntaje < 65


@pytest.fixture
def rutas_de(monkeypatch):
    """Recarga rutas con otras variables de entorno y la deja como estaba al terminar."""
    for variable in ("EMPLEO_PERFIL", "EMPLEO_EMPRESAS", "EMPLEO_SALIDA", "EMPLEO_BASE"):
        monkeypatch.delenv(variable, raising=False)

    def recargar(persona: str):
        monkeypatch.setenv("EMPLEO_PERSONA", persona)
        return importlib.reload(rutas)

    yield recargar
    monkeypatch.undo()
    importlib.reload(rutas)


def test_each_person_has_their_own_files(rutas_de):
    r = rutas_de("Ana")

    assert r.PERSONA == "ana"
    assert r.PERFIL == r.RAIZ / "perfil" / "ana" / "perfil.yaml"
    assert r.EMPRESAS == r.RAIZ / "perfil" / "ana" / "empresas.yaml"
    assert r.SALIDA == r.RAIZ / "salida" / "ana"
    assert r.BASE == r.RAIZ / "datos" / "ana.db"


def test_a_person_name_cannot_leave_the_project(rutas_de):
    with pytest.raises(ValueError):
        rutas_de("../otra")
