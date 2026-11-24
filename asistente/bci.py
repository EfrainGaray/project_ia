"""Lee ofertas públicas de Bci (trabajaenbci.cl) y las guarda en el modelo común de ofertas.

El sitio es una aplicación web que obtiene sus datos de una API JSON pública, sin sesión:
listado ``POST /api/v3/bci_portals/_search`` y ficha ``GET /api/v3/bci_portals/proceso/<id>``.
"""

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup

from asistente.ofertas import FalloFuente, guardar, importar_fuentes

FUENTE = "bci"
EMPRESA = "Bci"
HOST = "trabajaenbci.cl"
ROBOTS = f"https://{HOST}/robots.txt"
SEARCH = f"https://{HOST}/api/v3/bci_portals/_search"
DETAIL = f"https://{HOST}/api/v3/bci_portals/proceso/{{}}"
OFFER = f"https://{HOST}/offers/proceso/{{}}"
AGENT = "AsistentePostulaciones"
POR_PAGINA = 20
DETAIL_PATH = re.compile(r"/api/v3/bci_portals/proceso/([0-9]+)")
PUBLIC_PATH = re.compile(r"/offers/proceso/([0-9]+)")
SECCIONES = (
    ("Descripción", ("introduction", "full_description", "postulation_process_long_description")),
    ("Funciones", ("cleaned_main_functions", "main_functions")),
    ("Requisitos", ("excluding_requirements",)),
    ("Deseable", ("desirable_knowledge",)),
    ("Condiciones", ("job_conditions",)),
)


def public_url(url):
    parts = urlsplit(url)
    return (
        parts.scheme == "https"
        and parts.netloc == HOST
        and not parts.query
        and (parts.path in {"/robots.txt", urlsplit(SEARCH).path} or bool(DETAIL_PATH.fullmatch(parts.path)))
    )


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Portal:
    def __init__(self, opener=None, sleep=time.sleep):
        self.opener = opener or build_opener(NoRedirect())
        self.sleep = sleep
        self.robots = RobotFileParser()
        self.robots.parse(self.fetch(ROBOTS, robots=False).splitlines())
        self.delay = max(1.0, float(self.robots.crawl_delay(AGENT) or 0))

    def fetch(self, url, body=None, robots=True):
        if not public_url(url):
            raise FalloFuente("La dirección está fuera de las páginas públicas admitidas.", url)
        if robots:
            if not self.robots.can_fetch(AGENT, url):
                raise FalloFuente("robots.txt restringe la lectura de esta página.", url)
            self.sleep(self.delay)
        headers = {"User-Agent": AGENT, "Accept": "application/json"}
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        try:
            with self.opener.open(Request(url, data=data, headers=headers), timeout=15) as response:
                limit = 2_000_000
                raw = response.read(limit + 1)
                if len(raw) > limit:
                    raise FalloFuente("La respuesta supera el tamaño esperado.", url)
                return raw.decode(response.headers.get_content_charset() or "utf-8")
        except HTTPError as error:
            raise FalloFuente(f"Bci devolvió HTTP {error.code} ({motivo_http(error)}) para {url}.",
                              url, error.code) from error
        except URLError as error:
            raise FalloFuente(f"No se pudo conectar con Bci: {error.reason}.", url) from error

    def fetch_json(self, url, body=None):
        text = self.fetch(url, body)
        try:
            return json.loads(text)
        except json.JSONDecodeError as error:
            raise FalloFuente("La respuesta de Bci no es JSON; la ruta pudo cambiar.", url) from error


def motivo_http(error):
    try:
        detail = json.loads(error.read(10_000).decode("utf-8")).get("errors")
    except (ValueError, AttributeError, OSError):
        detail = None
    return str(detail or error.reason)


def fecha_iso(texto):
    try:
        return datetime.strptime(str(texto).strip(), "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def parse_listing(data):
    try:
        hits = data["hits"]["hits"]
        total = int(data["hits"]["total"])
    except (KeyError, TypeError, ValueError) as error:
        raise FalloFuente("El JSON no contiene el listado público de Bci.") from error
    ofertas = []
    for hit in hits:
        source = hit.get("_source") or {}
        match = PUBLIC_PATH.fullmatch(str(source.get("public_url", "")))
        title = str(source.get("title") or "").strip()
        if not match or not title or str(source.get("postulation_process_id")) != match[1]:
            continue
        ofertas.append({
            "fuente": FUENTE,
            "id_origen": match[1],
            "empresa": EMPRESA,
            "cargo": title,
            "ubicacion": (source.get("address") or "").strip() or None,
            "fecha_publicacion": fecha_iso(source.get("published_at_date_text")),
            "enlace": OFFER.format(match[1]),
            "descripcion": None,
        })
    return ofertas, total


def html_text(html):
    page = BeautifulSoup(html, "html.parser")
    for node in page.select("script, style"):
        node.decompose()
    for item in page.select("li"):
        item.insert_before("\n")
    lines = (re.sub(r"\s+", " ", line.replace("﻿", "")).strip() for line in page.get_text("\n").splitlines())
    return "\n".join(line for line in lines if line)


def parse_detail(data):
    if not isinstance(data, dict):
        raise FalloFuente("El JSON de la ficha de Bci no es un objeto.")
    partes = []
    for titulo, campos in SECCIONES:
        texto = next((html_text(data[c]) for c in campos if data.get(c) and html_text(data[c])), "")
        if texto:
            partes.append(f"{titulo}\n{texto}")
    if not any(p.startswith(("Descripción", "Funciones", "Requisitos")) for p in partes):
        raise FalloFuente("La ficha de Bci no contiene una descripción reconocible.")
    return "\n\n".join(partes)


def leer(portal, paginas=1, detalles=0):
    """Devuelve (ofertas, fallos parciales). Un fallo del listado detiene la fuente."""
    ofertas: dict[str, dict] = {}
    pagina, total = 0, None
    while pagina < paginas and (total is None or pagina * POR_PAGINA < total):
        body = {"size": POR_PAGINA, "from": pagina * POR_PAGINA}
        rows, total = parse_listing(portal.fetch_json(SEARCH, body))
        ofertas.update((row["id_origen"], row) for row in rows)
        pagina += 1
    parciales = []
    for oferta in list(ofertas.values())[:detalles]:
        url = DETAIL.format(oferta["id_origen"])
        try:
            oferta["descripcion"] = parse_detail(portal.fetch_json(url))
        except FalloFuente as error:
            error.url = error.url or url
            parciales.append(error)
    return list(ofertas.values()), parciales


def leer_guardado(listados, fichas=None):
    ofertas: dict[str, dict] = {}
    for path in listados:
        rows, _ = parse_listing(json.loads(path.read_text(encoding="utf-8-sig")))
        ofertas.update((row["id_origen"], row) for row in rows)
    parciales = []
    if fichas:
        for oferta in ofertas.values():
            path = fichas / f"proceso_{oferta['id_origen']}.json"
            if path.is_file():
                try:
                    oferta["descripcion"] = parse_detail(json.loads(path.read_text(encoding="utf-8-sig")))
                except FalloFuente as error:
                    error.url = str(path)
                    parciales.append(error)
    return list(ofertas.values()), parciales


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bd", type=Path, default=Path("postulaciones.sqlite3"))
    parser.add_argument("--json", type=Path, nargs="+", help="Respuestas del listado guardadas como JSON.")
    parser.add_argument("--fichas", type=Path, help="Carpeta con fichas guardadas como proceso_<ID>.json.")
    parser.add_argument("--paginas", type=int, default=1, choices=range(1, 6))
    parser.add_argument("--detalles", type=int, default=3, choices=range(0, 21),
                        help="Máximo de fichas en vivo que se consultarán.")
    args = parser.parse_args()

    leidas: list[dict] = []

    def fuente():
        if args.json:
            found = leer_guardado(args.json, args.fichas)
        else:
            found = leer(Portal(), args.paginas, args.detalles)
        leidas.extend(found[0])
        return found

    resumen = importar_fuentes(args.bd, {FUENTE: fuente})[FUENTE]
    for oferta in leidas:
        estado = "completa" if oferta["descripcion"] else "pendiente de descripción"
        print(f"{oferta['id_origen']} · {oferta['cargo']} · {estado} · {oferta['enlace']}")
    for motivo in resumen["fallos"]:
        print(f"Fallo registrado: {motivo}")
    total = guardar(args.bd, [])
    print(f"Ofertas leídas de Bci: {resumen['ofertas']} · Total de ofertas en SQLite: {total}")
    if resumen["ofertas"] == 0 and resumen["fallos"]:
        parser.exit(1)


if __name__ == "__main__":
    main()
