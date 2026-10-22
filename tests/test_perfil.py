"""El perfil: el ejemplo carga y los datos derivados salen bien."""

from empleo import rutas, vocabulario
from empleo.perfil import (
    anios_de_experiencia,
    cargar,
    ciudad_base,
    nombre_archivo,
    resumen_para_el_agente,
    salida_ultimo_empleo,
)


def test_the_example_profile_is_complete():
    perfil = cargar(rutas.PERFIL_EJEMPLO)
    resumen = resumen_para_el_agente(perfil)

    assert resumen["nombre"] == "Alex Ejemplo Prueba"
    assert resumen["contacto"]["correo"].endswith("@example.com")
    assert resumen["experiencia"] and resumen["proyectos"]
    assert anios_de_experiencia(perfil) > 5


def test_file_names_and_city_come_from_the_profile():
    perfil = {"datos": {"nombre": "Ana María Pérez", "ciudad": "Pasto, Colombia · Remoto"}}

    assert nombre_archivo(perfil) == "Ana-Maria-Perez"
    assert ciudad_base(perfil) == "Pasto"
    assert ciudad_base({**perfil, "objetivo": {"ciudad": "Cali"}}) == "Cali"


def test_any_salida_key_is_understood():
    assert salida_ultimo_empleo({"salida_ultimo_empleo": "a"}) == "a"
    assert salida_ultimo_empleo({"salida_mi_empresa": "b"}) == "b"
    assert salida_ultimo_empleo({}) is None


def test_skills_default_or_from_the_profile():
    assert vocabulario.del_perfil({}) == (vocabulario.DOMINA, vocabulario.LENGUAJES_SUYOS)

    domina, lenguajes = vocabulario.del_perfil(
        {"vocabulario": {"domina": ["go", "no-existe"], "lenguajes": ["go"]}}
    )

    assert domina == {"go"}
    assert lenguajes == {"go"}
