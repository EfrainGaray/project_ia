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

HOST = "trabajaenitau.cl"
SEARCH = f"https://{HOST}/search"
AGENT = "AsistentePostulaciones"
JOB_PATH = re.compile(r"/job/(?:[^/]+/)*([0-9]+)/?")
UPSERT = """
    INSERT INTO ofertas_itau (id, titulo, url, ubicacion, fecha, descripcion)
    VALUES (:id, :titulo, :url, :ubicacion, :fecha, :descripcion)
    ON CONFLICT(id) DO UPDATE SET
        titulo = excluded.titulo,
        url = excluded.url,
        ubicacion = COALESCE(excluded.ubicacion, ofertas_itau.ubicacion),
        fecha = COALESCE(excluded.fecha, ofertas_itau.fecha),
        descripcion = COALESCE(excluded.descripcion, ofertas_itau.descripcion)
"""


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
        self.delay = max(1, self.robots.crawl_delay(AGENT) or 0)

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
            raise ValueError(f"Itaú devolvió HTTP {error.code} para {url}.") from error


def parse_search(html):
    page = BeautifulSoup(html, "html.parser")
    table = page.select_one("#searchresults")
    if table is None:
        raise ValueError("El HTML no contiene el listado público de Itaú.")
    jobs = []
    for row in table.select("tr"):
        cells = row.find_all("td", recursive=False)
        for link in row.select("a[href]"):
            parts = urlsplit(urljoin(SEARCH, link["href"]))
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
        url = urljoin(SEARCH, link["href"])
        parts = urlsplit(url)
        if parts.path == "/search" and "startrow=" in parts.query and public_url(url):
            next_pages.append(url)
    return jobs, next_pages


def parse_detail(html):
    page = BeautifulSoup(html, "html.parser")
    description = page.select_one(
        '[itemprop="description"], .jobdescription, .job-description, [data-careersite-propertyid="description"]'
    )
    if description is None or not description.get_text(strip=True):
        raise ValueError("El HTML de la ficha no contiene una descripción reconocible.")
    for node in description.select("script, style"):
        node.decompose()
    return description.get_text("\n", strip=True)


def save(database, jobs):
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS ofertas_itau (
                id TEXT PRIMARY KEY, titulo TEXT NOT NULL, url TEXT NOT NULL,
                ubicacion TEXT, fecha TEXT, descripcion TEXT
            )
        """)
        db.executemany(UPSERT, jobs)
        return db.execute("SELECT COUNT(*) FROM ofertas_itau").fetchone()[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bd", type=Path, default=Path("postulaciones.sqlite3"))
    parser.add_argument("--html", type=Path, nargs="+", help="Listados guardados en el navegador.")
    parser.add_argument("--fichas", type=Path, help="Carpeta opcional de fichas guardadas como ID.html.")
    parser.add_argument("--paginas", type=int, default=2, choices=range(1, 6))
    parser.add_argument("--detalles", type=int, default=0, choices=range(0, 11),
                        help="Máximo de fichas en vivo que se consultarán.")
    args = parser.parse_args()
    if args.html and args.detalles:
        parser.error("Para HTML guardado, usa --fichas en lugar de --detalles.")
    try:
        jobs = {}
        if args.html:
            for path in args.html:
                rows, _ = parse_search(path.read_text(encoding="utf-8-sig"))
                jobs.update((row["id"], row) for row in rows)
        else:
            portal = Portal()
            pending = [SEARCH]
            visited = set()
            while pending and len(visited) < args.paginas:
                url = pending.pop(0)
                visited.add(url)
                rows, links = parse_search(portal.fetch(url))
                jobs.update((row["id"], row) for row in rows)
                pending.extend(link for link in dict.fromkeys(links)
                               if link not in visited and link not in pending)
            for job in list(jobs.values())[:args.detalles]:
                job["descripcion"] = parse_detail(portal.fetch(job["url"]))
        if args.fichas:
            for job in jobs.values():
                path = args.fichas / f"{job['id']}.html"
                if path.is_file():
                    job["descripcion"] = parse_detail(path.read_text(encoding="utf-8-sig"))
        total = save(args.bd, jobs.values())
    except (OSError, URLError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Error: {error}\n")
    for job in jobs.values():
        print(f"{job['id']} · {job['titulo']} · {job['url']}")
    print(f"Ofertas leídas: {len(jobs)} · Total Itaú en SQLite: {total}")


if __name__ == "__main__":
    main()
