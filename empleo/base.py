"""Lo que se guarda: ofertas vistas, postulaciones con su historial y cuándo se
consultó cada fuente. Un SQLite local en datos/empleo.db."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from empleo import rutas
from empleo.ajuste import Analisis
from empleo.fuentes import Oferta

ESTADOS = [
    "guardada",  # interesa, todavía no se prepara nada
    "preparada",  # hoja de vida (y carta) listas para enviar
    "postulada",
    "entrevista",
    "prueba_tecnica",
    "oferta",
    "aceptada",
    "rechazada",
    "descartada",
]
ABIERTOS = [
    "guardada",
    "preparada",
    "postulada",
    "entrevista",
    "prueba_tecnica",
    "oferta",
]

ESQUEMA = """
CREATE TABLE IF NOT EXISTS ofertas (
    id TEXT PRIMARY KEY,
    fuente TEXT NOT NULL,
    id_externo TEXT NOT NULL,
    titulo TEXT NOT NULL,
    empresa TEXT NOT NULL,
    url TEXT NOT NULL,
    descripcion TEXT NOT NULL DEFAULT '',
    ubicacion TEXT NOT NULL DEFAULT '',
    remoto INTEGER,
    salario_min REAL,
    salario_max REAL,
    moneda TEXT,
    periodo TEXT,
    publicada TEXT,
    idioma TEXT,
    etiquetas TEXT NOT NULL DEFAULT '[]',
    puntaje INTEGER NOT NULL DEFAULT 0,
    analisis TEXT NOT NULL DEFAULT '{}',
    vista TEXT NOT NULL,
    descartada INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS postulaciones (
    oferta_id TEXT PRIMARY KEY REFERENCES ofertas(id),
    estado TEXT NOT NULL,
    carpeta TEXT,
    nota TEXT NOT NULL DEFAULT '',
    proxima_accion TEXT,
    creada TEXT NOT NULL,
    actualizada TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS historial (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    oferta_id TEXT NOT NULL REFERENCES ofertas(id),
    fecha TEXT NOT NULL,
    estado TEXT NOT NULL,
    nota TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS consultas (
    fuente TEXT NOT NULL,
    consulta TEXT NOT NULL,
    fecha TEXT NOT NULL,
    PRIMARY KEY (fuente, consulta)
);
"""


def ahora() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Base:
    def __init__(self, ruta: Path | None = None) -> None:
        ruta = ruta or rutas.BASE  # se lee al usar: las pruebas la cambian
        ruta.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(ruta)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(ESQUEMA)

    # --- Ofertas -------------------------------------------------------------------

    def guardar_oferta(self, oferta: Oferta, analisis: Analisis) -> None:
        """Guarda o actualiza; conserva cuándo se vio por primera vez y si se descartó."""
        self.con.execute(
            """
            INSERT INTO ofertas (id, fuente, id_externo, titulo, empresa, url, descripcion, ubicacion,
                remoto, salario_min, salario_max, moneda, periodo, publicada, idioma, etiquetas,
                puntaje, analisis, vista)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                titulo=excluded.titulo, empresa=excluded.empresa, url=excluded.url,
                descripcion=excluded.descripcion, ubicacion=excluded.ubicacion,
                remoto=excluded.remoto, salario_min=excluded.salario_min,
                salario_max=excluded.salario_max, moneda=excluded.moneda,
                periodo=excluded.periodo, publicada=excluded.publicada, idioma=excluded.idioma,
                etiquetas=excluded.etiquetas, puntaje=excluded.puntaje, analisis=excluded.analisis
            """,
            (
                oferta.id, oferta.fuente, oferta.id_externo, oferta.titulo, oferta.empresa,
                oferta.url, oferta.descripcion, oferta.ubicacion,
                None if oferta.remoto is None else int(oferta.remoto),
                oferta.salario_min, oferta.salario_max, oferta.moneda, oferta.periodo,
                oferta.publicada, analisis.idioma, json.dumps(oferta.etiquetas, ensure_ascii=False),
                analisis.puntaje, json.dumps(analisis.como_dict(), ensure_ascii=False), ahora(),
            ),
        )  # fmt: skip
        self.con.commit()

    def oferta(self, oferta_id: str) -> dict | None:
        fila = self.con.execute("SELECT * FROM ofertas WHERE id = ?", (oferta_id,)).fetchone()
        return dict(fila) if fila else None

    def ofertas(
        self, dias: int = 45, minimo: int = 0, incluir_descartadas: bool = False
    ) -> list[dict]:
        desde = (datetime.now(UTC) - timedelta(days=dias)).isoformat()
        filas = self.con.execute(
            """
            SELECT o.*, p.estado AS estado_postulacion FROM ofertas o
            LEFT JOIN postulaciones p ON p.oferta_id = o.id
            WHERE o.vista >= ? AND o.puntaje >= ? AND (? OR o.descartada = 0)
            ORDER BY o.puntaje DESC, o.vista DESC
            """,
            (desde, minimo, int(incluir_descartadas)),
        ).fetchall()
        return [dict(f) for f in filas]

    def desactualizadas(self, version: int) -> list[dict]:
        """Ofertas calificadas con reglas viejas."""
        filas = self.con.execute(
            "SELECT * FROM ofertas WHERE coalesce(json_extract(analisis, '$.version'), 0) != ?",
            (version,),
        ).fetchall()
        return [dict(f) for f in filas]

    def descartar(self, oferta_id: str) -> None:
        self.con.execute("UPDATE ofertas SET descartada = 1 WHERE id = ?", (oferta_id,))
        self.con.commit()

    def misma_oferta(self, empresa: str, titulo: str) -> str | None:
        """La misma vacante publicada en otra fuente."""
        fila = self.con.execute(
            "SELECT id FROM ofertas WHERE lower(empresa) = lower(?) AND lower(titulo) = lower(?)",
            (empresa.strip(), titulo.strip()),
        ).fetchone()
        return fila["id"] if fila else None

    # --- Consultas a las fuentes -----------------------------------------------------

    def consulta_reciente(self, fuente: str, consulta: str, horas: int = 6) -> bool:
        fila = self.con.execute(
            "SELECT fecha FROM consultas WHERE fuente = ? AND consulta = ?",
            (fuente, consulta.lower()),
        ).fetchone()
        if not fila:
            return False
        return datetime.fromisoformat(fila["fecha"]) > datetime.now(UTC) - timedelta(hours=horas)

    def anotar_consulta(self, fuente: str, consulta: str) -> None:
        self.con.execute(
            "INSERT OR REPLACE INTO consultas (fuente, consulta, fecha) VALUES (?, ?, ?)",
            (fuente, consulta.lower(), ahora()),
        )
        self.con.commit()

    # --- Postulaciones -----------------------------------------------------------------

    def postulacion(self, oferta_id: str) -> dict | None:
        fila = self.con.execute(
            "SELECT * FROM postulaciones WHERE oferta_id = ?", (oferta_id,)
        ).fetchone()
        return dict(fila) if fila else None

    def cambiar_estado(
        self,
        oferta_id: str,
        estado: str,
        nota: str = "",
        proxima_accion: date | None = None,
        carpeta: str | None = None,
    ) -> dict:
        if estado not in ESTADOS:
            raise ValueError(f"Estado desconocido: {estado}. Válidos: {', '.join(ESTADOS)}")
        if self.oferta(oferta_id) is None:
            raise ValueError(f"No conozco la oferta {oferta_id}.")
        momento = ahora()
        actual = self.postulacion(oferta_id)
        if actual is None:
            self.con.execute(
                "INSERT INTO postulaciones (oferta_id, estado, carpeta, nota, proxima_accion, creada, actualizada)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    oferta_id,
                    estado,
                    carpeta,
                    nota,
                    _fecha(proxima_accion),
                    momento,
                    momento,
                ),
            )
        else:
            self.con.execute(
                "UPDATE postulaciones SET estado = ?, carpeta = COALESCE(?, carpeta),"
                " nota = CASE WHEN ? = '' THEN nota ELSE ? END,"
                " proxima_accion = ?, actualizada = ? WHERE oferta_id = ?",
                (
                    estado,
                    carpeta,
                    nota,
                    nota,
                    _fecha(proxima_accion),
                    momento,
                    oferta_id,
                ),
            )
        self.con.execute(
            "INSERT INTO historial (oferta_id, fecha, estado, nota) VALUES (?, ?, ?, ?)",
            (oferta_id, momento, estado, nota),
        )
        self.con.commit()
        return self.postulacion(oferta_id) or {}

    def postulaciones(self, estado: str | None = None) -> list[dict]:
        filas = self.con.execute(
            """
            SELECT p.*, o.titulo, o.empresa, o.url, o.puntaje FROM postulaciones p
            JOIN ofertas o ON o.id = p.oferta_id
            WHERE (? IS NULL OR p.estado = ?)
            ORDER BY p.actualizada DESC
            """,
            (estado, estado),
        ).fetchall()
        return [dict(f) for f in filas]

    def historial(self, oferta_id: str) -> list[dict]:
        filas = self.con.execute(
            "SELECT fecha, estado, nota FROM historial WHERE oferta_id = ? ORDER BY id",
            (oferta_id,),
        ).fetchall()
        return [dict(f) for f in filas]


def _fecha(valor: date | None) -> str | None:
    return valor.isoformat() if valor else None
