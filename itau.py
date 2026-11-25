"""Lee ofertas públicas de Itaú y las guarda en SQLite."""

import argparse
import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from asistente import ofertas

HOST = "trabajaenitau.cl"
SEARCH = f"https://{HOST}/search"
AGENT = "AsistentePostulaciones"
JOB_PATH = re.compile(r"/job/(?:[^/]+/)*([0-9]+)/?")
FUENTE = "itau"
EMPRESA = "Itaú"


def public_url(url):
    parts = urlsplit(url)
    return (
        parts.scheme == "https"
        and parts.netloc == HOST
        and (parts.path in {"/search", "/robots.txt"} or JOB_PATH.fullmatch(parts.path))
    )


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Portal:
    def __init__(self):
        self.opener = build_opener(NoRedirect())
        rules = self.fetch(f"https://{HOST}/robots.txt")
        self.robots = RobotFileParser()
        self.robots.parse(rules.splitlines())
        self.delay = max(1.0, float(self.robots.crawl_delay(AGENT) or 0))

    def fetch(self, url):
        if not public_url(url):
            raise ValueError("La dirección está fuera de las páginas públicas admitidas.")
        if hasattr(self, "robots"):
            if not self.robots.can_fetch(AGENT, url):
                raise ValueError("robots.txt restringe la lectura de esta página.")
            time.sleep(self.delay)
        request = Request(url, headers={"User-Agent": AGENT})
        try:
            with self.opener.open(request, timeout=15) as response:
                limit = 2_000_000
                body = response.read(limit + 1)
                if len(body) > limit:
                    raise ValueError("La página supera el tamaño esperado.")
                return body.decode(response.headers.get_content_charset() or "utf-8")
        except HTTPError as error:
            motivo = f"Itaú devolvió HTTP {error.code} para {url}."
            raise ofertas.FalloFuente(motivo, url, error.code) from error


def parse_search(html):
    page = BeautifulSoup(html, "html.parser")
    table = page.select_one("#searchresults")
    if table is None:
        raise ValueError("El HTML no contiene el listado público de Itaú.")
    jobs = []
    for row in table.select("tr"):
        cells = row.find_all("td", recursive=False)
        for link in row.select("a[href]"):
            parts = urlsplit(urljoin(SEARCH, str(link["href"])))
            url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
            match = JOB_PATH.fullmatch(parts.path)
            title = link.get_text(" ", strip=True)
            if match and title and public_url(url):
                jobs.append({
                    "id": match[1],
                    "titulo": title,
                    "url": url,
                    "ubicacion": cells[1].get_text(" ", strip=True) if len(cells) > 1 else None,
                    "fecha": cells[2].get_text(" ", strip=True) if len(cells) > 2 else None,
                    "descripcion": None,
                })
                break
    next_pages = []
    for link in page.select("a[href]"):
        url = urljoin(SEARCH, str(link["href"]))
        parts = urlsplit(url)
        if parts.path == "/search" and "startrow=" in parts.query and public_url(url):
            next_pages.append(url)
    return jobs, next_pages


def parse_detail(html):
    page = BeautifulSoup(html, "html.parser")
    description = page.select_one(
        '[itemprop="description"], .jobdescription, .job-description, '
        '[data-careersite-propertyid="description"]'
    )
    if description is None or not description.get_text(strip=True):
        raise ValueError("El HTML de la ficha no contiene una descripción reconocible.")
    for node in description.select("script, style"):
        node.decompose()
    return description.get_text("\n", strip=True)


def migrar(database):
    """Copia los registros históricos que todavía no están en la tabla común."""
    with closing(ofertas.conectar(database)) as db, db:
        tabla = db.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='ofertas_itau'"
        ).fetchone()
        if tabla is None:
            return 0
        ahora = ofertas.ahora()
        db.execute("""
            INSERT INTO ofertas (
                fuente, id_origen, empresa, cargo, ubicacion, fecha_publicacion,
                fecha_deteccion, fecha_actualizacion, enlace, descripcion, estado
            )
            SELECT ?, id, ?, titulo, ubicacion, fecha, ?, ?, url,
                   CASE WHEN TRIM(descripcion) <> '' THEN descripcion END,
                   CASE WHEN TRIM(descripcion) <> '' THEN ? ELSE ? END
            FROM ofertas_itau WHERE id IS NOT NULL
            ON CONFLICT(fuente, id_origen) DO NOTHING
        """, (FUENTE, EMPRESA, ahora, ahora, ofertas.COMPLETA, ofertas.PENDIENTE))
        return db.execute("SELECT changes()").fetchone()[0]


def save(database, jobs):
    migrar(database)
    ofertas.guardar(database, ({
        "fuente": FUENTE, "empresa": EMPRESA, "id_origen": job["id"], "cargo": job["titulo"],
        "enlace": job["url"], "ubicacion": job.get("ubicacion"), "fecha_publicacion": job.get("fecha"),
        "descripcion": job.get("descripcion"),
    } for job in jobs))
    with closing(ofertas.conectar(database)) as db:
        return db.execute("SELECT COUNT(*) FROM ofertas WHERE fuente = ?", (FUENTE,)).fetchone()[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bd", type=Path, default=Path("postulaciones.sqlite3"))
    parser.add_argument("--html", type=Path, nargs="+", help="Listados guardados en el navegador.")
    parser.add_argument("--fichas", type=Path, help="Carpeta opcional de fichas guardadas como ID.html.")
    parser.add_argument("--paginas", type=int, default=2, choices=range(1, 6))
    parser.add_argument("--detalles", type=int, default=0, choices=range(0, 11),
                        help="Máximo de fichas en vivo que se consultarán.")
    parser.add_argument("--solo-migrar", action="store_true",
                        help="Copia ofertas históricas sin consultar el portal.")
    args = parser.parse_args()
    if args.html and args.detalles:
        parser.error("Para HTML guardado, usa --fichas en lugar de --detalles.")
    url = SEARCH
    try:
        migradas = migrar(args.bd)
        if args.solo_migrar:
            print(f"Ofertas históricas copiadas: {migradas}")
            return
        jobs: dict[str, dict] = {}
        if args.html:
            for path in args.html:
                rows, _ = parse_search(path.read_text(encoding="utf-8-sig"))
                jobs.update((row["id"], row) for row in rows)
        else:
            portal = Portal()
            pending = [SEARCH]
            visited: set[str] = set()
            while pending and len(visited) < args.paginas:
                url = pending.pop(0)
                visited.add(url)
                rows, links = parse_search(portal.fetch(url))
                jobs.update((row["id"], row) for row in rows)
                pending.extend(link for link in dict.fromkeys(links)
                               if link not in visited and link not in pending)
            for job in list(jobs.values())[:args.detalles]:
                url = job["url"]
                job["descripcion"] = parse_detail(portal.fetch(url))
        if args.fichas:
            for job in jobs.values():
                path = args.fichas / f"{job['id']}.html"
                if path.is_file():
                    job["descripcion"] = parse_detail(path.read_text(encoding="utf-8-sig"))
        total = save(args.bd, jobs.values())
    except (ofertas.FalloFuente, OSError, URLError, ValueError) as error:
        if not args.html and not args.solo_migrar:
            fallo = error if isinstance(error, ofertas.FalloFuente) else ofertas.FalloFuente(str(error), url)
            try:
                ofertas.registrar_fallo(args.bd, FUENTE, fallo)
            except sqlite3.Error as registro:
                parser.exit(1, f"Error: {error} (fallo al registrar: {registro})\n")
        parser.exit(1, f"Error: {error}\n")
    except sqlite3.Error as error:
        parser.exit(1, f"Error: {error}\n")
    for job in jobs.values():
        print(f"{job['id']} · {job['titulo']} · {job['url']}")
    print(f"Ofertas leídas: {len(jobs)} · Total Itaú en SQLite: {total}")


if __name__ == "__main__":
    main()
