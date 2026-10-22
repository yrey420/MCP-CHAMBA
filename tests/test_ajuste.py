"""La calificación de una oferta: que premie lo que encaja con el perfil y avise lo que no."""

from empleo.ajuste import donde, evaluar, idioma_de, salario_mensual_usd

BACKEND = (
    "We're hiring a Senior Backend Engineer to build our multi-tenant SaaS with Python, Django and "
    "Django REST Framework on PostgreSQL. You'll design REST and GraphQL APIs, third-party "
    "integrations with OAuth2, deploy with Docker on AWS and write pytest suites. Bonus: LLMs, RAG."
)


def test_a_backend_offer_open_to_latam_scores_high():
    analisis = evaluar(
        "Senior Backend Engineer (Python/Django)",
        BACKEND,
        ubicacion="LATAM",
        remoto=True,
    )

    assert analisis.puntaje >= 80
    assert "Django" in analisis.coinciden
    assert analisis.remoto_desde_colombia == "si"
    assert analisis.etiquetas_cv[0] in {"backend", "integraciones"}


def test_a_us_only_offer_is_flagged():
    analisis = evaluar("Senior Backend Engineer", BACKEND, ubicacion="United States", remoto=True)

    assert analisis.remoto_desde_colombia == "no"
    assert analisis.puntaje < 60
    assert any("Colombia" in r for r in analisis.razones)


def test_must_live_in_the_us_also_counts_even_if_it_says_remote():
    texto = BACKEND + " Candidates must be located in the US."

    assert donde("Remote", True, texto) == "no"


def test_unknown_location_asks_to_confirm():
    analisis = evaluar("Backend Developer", BACKEND, ubicacion="", remoto=True)

    assert analisis.remoto_desde_colombia == "desconocido"
    assert any("confírmalo" in r for r in analisis.razones)


def test_frontend_or_junior_roles_score_lower():
    backend = evaluar(
        "Senior Backend Engineer", BACKEND, ubicacion="Worldwide", remoto=True
    ).puntaje

    assert (
        evaluar("Frontend Engineer", BACKEND, ubicacion="Worldwide", remoto=True).puntaje < backend
    )
    assert (
        evaluar("Junior Backend Developer", BACKEND, ubicacion="Worldwide", remoto=True).puntaje
        < backend
    )


def test_what_is_missing_and_what_is_close():
    texto = "Senior Backend Engineer. Go, FastAPI, Kafka and GCP. Kubernetes."

    analisis = evaluar("Senior Backend Engineer", texto, ubicacion="Worldwide", remoto=True)

    assert "Go" in analisis.faltan
    assert "Fastapi" in analisis.parecidas
    assert "Kubernetes" in analisis.coinciden


def test_too_many_years_weighs_against():
    analisis = evaluar("Backend Engineer", BACKEND + " 12+ years of experience.", "Worldwide", True)

    assert any("12 años" in r for r in analisis.razones)


def test_on_site_in_your_city_beats_moving_to_another():
    texto = "Desarrollador backend Python Django, presencial."
    aca = evaluar(
        "Desarrollador Backend", texto, "Manizales, Colombia", remoto=False, ciudad="Manizales"
    )
    alla = evaluar(
        "Desarrollador Backend", texto, "Bogotá, Colombia", remoto=False, ciudad="Manizales"
    )

    assert aca.puntaje > alla.puntaje
    assert any("mudarte" in r for r in alla.razones)


def test_low_pay_is_flagged():
    analisis = evaluar(
        "Backend Engineer",
        BACKEND,
        "Worldwide",
        True,
        salario=(800, 1000),
        expectativa_usd_mes=2163,
    )

    assert any("menos de lo que esperas" in r for r in analisis.razones)


def test_salaries_are_compared_in_dollars_per_month():
    assert salario_mensual_usd(120000, 150000, "USD", "yearly") == (10000, 12500)
    assert salario_mensual_usd(4000, 6500, "USD", "mes") == (4000, 6500)
    assert salario_mensual_usd(None, 9000000, "COP", "mes") == (2780, 2780)
    assert salario_mensual_usd(None, None, "USD", "mes") is None


def test_language_of_the_offer():
    assert (
        idioma_de("Buscamos un desarrollador backend con experiencia en Django para el equipo")
        == "es"
    )
    assert idioma_de(BACKEND) == "en"


def test_a_remote_offer_limited_to_one_country_is_flagged():
    for pais in ["Costa Rica", "Turkey", "South Africa", "Remote, France"]:
        assert donde(pais, True, BACKEND) == "no", pais
    assert donde("Northern America, LATAM", True, BACKEND) == "si"


def test_the_main_language_in_the_title_rules():
    texto = BACKEND + " Also .NET and C#."

    analisis = evaluar("Senior .NET Full-stack Developer", texto, "Worldwide", True)

    assert any("lenguaje principal es .NET / C#" in r for r in analisis.razones)
    assert (
        analisis.puntaje < evaluar("Senior Full-stack Developer", texto, "Worldwide", True).puntaje
    )


def test_an_unknown_language_label_is_detected_from_the_text():
    assert evaluar("Backend", BACKEND, idioma="lang_not_specified").idioma == "en"


def test_what_the_title_names_goes_first_on_the_cv():
    texto = (
        "LLMs, RAG and AI agents in production. Python, Docker, Kubernetes, AWS, CI/CD, Datadog."
    )

    analisis = evaluar("Senior AI Engineer (LLMs / RAG / AI Agents)", texto, "Remote", True)

    assert analisis.etiquetas_cv[0] == "ia"


def test_the_profile_can_bring_its_own_skills():
    texto = "Senior Backend Engineer. Go, gRPC, Kubernetes and PostgreSQL."

    general = evaluar("Senior Go Engineer", texto, "Worldwide", True)
    gopher = evaluar(
        "Senior Go Engineer",
        texto,
        "Worldwide",
        True,
        domina={"go", "grpc", "kubernetes", "postgresql"},
        lenguajes={"go"},
    )

    assert "Go" in general.faltan
    assert "Go" in gopher.coinciden
    assert gopher.puntaje > general.puntaje
