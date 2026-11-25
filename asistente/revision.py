"""Vista local de candidaturas y de los PDF configurados en el perfil."""

import argparse
import hashlib
import json
import sqlite3
from contextlib import closing
from html import escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit

from asistente import candidaturas

PERFIL_DEMO = Path("demo/perfil.json")


def _texto(valor: object) -> str:
    return escape(str(valor))


class ServidorRevision(ThreadingHTTPServer):
    def __init__(self, bd: Path, puerto: int, perfil: Path) -> None:
        datos = json.loads(perfil.read_text(encoding="utf-8"))
        self.pdfs = {
            version: (perfil.parent / datos_version["pdf"]).resolve()
            for version, datos_version in datos["versiones"].items()
        }
        self.evidencias: dict[str, str] = datos["evidencias"]
        self.bd = bd
        super().__init__(("127.0.0.1", puerto), VistaRevision)


def servidor(bd: Path, puerto: int = 8770, perfil: Path = PERFIL_DEMO) -> ServidorRevision:
    return ServidorRevision(bd, puerto, perfil)


class VistaRevision(BaseHTTPRequestHandler):
    server: ServidorRevision

    def _responder(
        self, cuerpo: bytes, codigo: HTTPStatus = HTTPStatus.OK, tipo: str = "text/html; charset=utf-8",
    ) -> None:
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _pagina(self, titulo: str, contenido: str, codigo: HTTPStatus = HTTPStatus.OK) -> None:
        self._responder(f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>{_texto(titulo)}</title>
</head><body><main>{contenido}</main></body></html>""".encode(), codigo)

    def _host_local(self) -> bool:
        host = self.headers.get_all("Host", [])
        if host == [f"127.0.0.1:{self.server.server_port}"] or host == ["127.0.0.1"]:
            return True
        self.send_error(HTTPStatus.FORBIDDEN)
        return False

    def do_GET(self) -> None:
        if not self._host_local():
            return
        url = urlsplit(self.path)
        partes = url.path.split("/")
        try:
            if url.path == "/":
                self._lista()
            elif len(partes) == 3 and partes[1] == "candidatura":
                self._detalle(int(partes[2]))
            elif len(partes) == 3 and partes[1] == "pdf":
                pdf = self._pdf(unquote(partes[2]), parse_qs(url.query))
                self._responder(pdf, tipo="application/pdf")
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except (ValueError, OSError):
            self.send_error(HTTPStatus.NOT_FOUND)
        except sqlite3.Error:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)

    def _lista(self) -> None:
        with closing(candidaturas._conectar(self.server.bd)) as db:
            filas = db.execute("SELECT id, cargo, estado FROM candidaturas ORDER BY id DESC").fetchall()
        enlaces = "".join(
            f'<li><a href="/candidatura/{fila["id"]}">{_texto(fila["cargo"])}</a>'
            f' · {_texto(fila["estado"])}</li>'
            for fila in filas
        )
        contenido = f"<ul>{enlaces}</ul>" if enlaces else "<p>Sin candidaturas guardadas.</p>"
        self._pagina("Candidaturas", f"<h1>Candidaturas</h1>{contenido}")

    def _pdf(self, version: str, consulta: dict[str, list[str]]) -> bytes:
        archivo = self.server.pdfs.get(version)
        if archivo is None:
            raise ValueError("Versión desconocida")
        pdf = archivo.read_bytes()
        if not pdf.startswith(b"%PDF-"):
            raise ValueError("Archivo PDF inválido")
        if consulta:
            fila = candidaturas.leer(self.server.bd, int(consulta.get("id", [""])[0]))
            if (
                version != fila["cv_version"] or str(archivo) != fila["archivo"]
                or consulta.get("huella") != [fila["huella"]]
                or hashlib.sha256(pdf).hexdigest() != fila["pdf_sha256"]
            ):
                raise ValueError("El PDF ya no coincide con la candidatura")
        return pdf

    def _detalle(self, identificador: int) -> None:
        fila = candidaturas.leer(self.server.bd, identificador)
        with closing(candidaturas._conectar(self.server.bd)) as db:
            oferta = db.execute(
                "SELECT empresa, enlace, descripcion FROM ofertas WHERE fuente=? AND id_origen=?",
                (fila["fuente"], fila["id_origen"]),
            ).fetchone()
            decision = db.execute(
                "SELECT requisitos FROM decisiones WHERE id=?", (fila["decision_id"],),
            ).fetchone()
        requisitos = "".join(
            f'<li>{_texto(row["tipo"])} · <q>{_texto(row["cita"])}</q>'
            f' · {_texto(self.server.evidencias.get(row.get("evidencia"), "Pendiente"))}</li>'
            for row in json.loads(decision["requisitos"])
        )
        respuestas = "".join(
            f'<li><strong>{_texto(campo)}</strong> · {_texto(valor)}'
            f'{" <strong>Pendiente</strong>" if campo in fila["pendientes"] else ""}</li>'
            for campo, valor in fila["respuestas"].items()
        )
        consulta = {"id": [str(identificador)], "huella": [fila["huella"]]}
        try:
            self._pdf(fila["cv_version"], consulta)
            ruta = f'/pdf/{quote(fila["cv_version"], safe="")}?{urlencode(consulta, doseq=True)}'
            pdf = f'<embed src="{_texto(ruta)}" type="application/pdf" title="Vista previa del CV">'
        except (OSError, ValueError):
            pdf = "<p>El PDF guardado falta o cambió. Actualiza la candidatura antes de aprobar.</p>"
        sin_descripcion = "<p>Oferta pendiente de descripción.</p>" if not oferta["descripcion"] else ""
        self._pagina(fila["cargo"], f"""
<p><a href="/">Candidaturas</a></p><h1>{_texto(fila["cargo"])}</h1>
<p>{_texto(oferta["empresa"])} · {_texto(fila["estado"])}</p>
<p>Oferta: {_texto(oferta["enlace"])}</p>{sin_descripcion}
<p>Destino: {_texto(fila["destino"])}</p>
<h2>Requisitos</h2><ul>{requisitos}</ul>
<h2>CV</h2><p>{_texto(Path(fila["archivo"]).name)}</p>{pdf}
<h2>Respuestas</h2><ul>{respuestas}</ul>
<p>Huella <code>{_texto(fila["huella"])}</code></p>""")


def main() -> None:
    parser = argparse.ArgumentParser(description="Abre la vista local de candidaturas.")
    parser.add_argument("--bd", type=Path, default=Path("postulaciones.sqlite3"))
    parser.add_argument("--puerto", type=int, default=8770)
    parser.add_argument("--perfil", type=Path, default=PERFIL_DEMO)
    args = parser.parse_args()
    try:
        with servidor(args.bd, args.puerto, args.perfil) as vista:
            print(f"http://127.0.0.1:{vista.server_port}", flush=True)
            vista.serve_forever()
    except (OSError, ValueError) as error:
        parser.exit(1, f"Error: {error}\n")
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
