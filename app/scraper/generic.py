from __future__ import annotations
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import trafilatura
import logging

from app.config import settings
from app.scraper.base import BaseScraper, Article
from app.services.news_service import upsert_noticia
from app.database import get_db

logger = logging.getLogger("nexnews.scraper")


# -------------------------------
# 🔍 Funciones auxiliares
# -------------------------------
def same_domain(url_a: str, url_b: str) -> bool:
    """Verifica si dos URLs pertenecen al mismo dominio."""
    pa, pb = urlparse(url_a), urlparse(url_b)
    return pa.netloc == pb.netloc


def is_probable_article(href: str) -> bool:
    """Heurísticas simples para identificar enlaces a artículos."""
    if not href:
        return False
    href = href.lower()

    # Excluir rutas comunes no relacionadas con noticias
    bad = [
        "#", "mailto:", "javascript:", "/tag/", "/etiqueta/", "/categoria/",
        "/category/", "/search", "/autor/", "/author/", "/seccion/", "/opinion/"
    ]
    if any(x in href for x in bad):
        return False

    # URLs con fecha o slugs típicos de noticias
    return bool(re.search(r"/20\d{2}/|/noticia|/news|/articulo|/nota|/politica|/deportes|/economia", href))


def extract_meta(soup: BeautifulSoup, base_url: str):
    """Extrae metadatos relevantes (título, imagen, fecha) del HTML."""
    def meta(name: str):
        og = soup.find("meta", property=f"og:{name}")
        if og and og.get("content"):
            return og["content"].strip()
        nn = soup.find("meta", attrs={"name": name})
        return nn["content"].strip() if nn and nn.get("content") else None

    title = soup.title.string.strip() if soup.title and soup.title.string else None
    title = meta("title") or title
    image = meta("image")

    # Intentar extraer fecha de publicación
    dt = None
    time_tag = soup.find("time")
    if time_tag and time_tag.get("datetime"):
        try:
            dt = datetime.fromisoformat(time_tag["datetime"].replace("Z", "+00:00"))
        except Exception:
            dt = None

    return title, image, dt


# -------------------------------
# 📰 Clase principal del scraper
# -------------------------------
class GenericScraper(BaseScraper):
    def __init__(self, listado_url: str):
        super().__init__()
        self.listado_url = listado_url

    def parse_listing(self) -> list[str]:
        """Obtiene los enlaces de artículos desde la página de listado."""
        logger.info(f"🔗 Analizando listado: {self.listado_url}")
        try:
            html = self.fetch(self.listado_url)
        except Exception as e:
            logger.error(f"[❌ ERROR] No se pudo obtener el listado de {self.listado_url}: {e}")
            return []

        soup = BeautifulSoup(html, "html.parser")
        links = []

        for a in soup.find_all("a", href=True):
            href = urljoin(self.listado_url, a["href"])
            if same_domain(self.listado_url, href) and is_probable_article(href):
                clean_href = href.split("#")[0]
                if clean_href not in links:
                    links.append(clean_href)

        logger.info(f"✅ Se encontraron {len(links)} posibles artículos.")
        return links[:50]  # Límite razonable

    def parse_article(self, url: str) -> Article | None:
        """Descarga y analiza un artículo individual."""
        logger.debug(f"📰 Extrayendo artículo: {url}")
        try:
            html = self.fetch(url)
        except Exception as e:
            logger.warning(f"[⚠️ ERROR] No se pudo descargar el artículo {url}: {e}")
            return None

        soup = BeautifulSoup(html, "html.parser")
        title_meta, image_meta, dt_meta = extract_meta(soup, url)

        # Extraer contenido con trafilatura
        extracted = trafilatura.extract(html, include_comments=False, include_tables=False)
        if not extracted:
            logger.warning(f"[⚠️ AVISO] No se pudo extraer contenido de {url}")
            return None

        fuente = urlparse(url).netloc

        return Article(
            url=url,
            fuente=fuente,
            titulo=title_meta or extracted.split("\n")[0][:180],
            contenido=extracted,
            fecha_publicacion=dt_meta,
            imagen_url=image_meta,
        )

    def scrape_and_store(self) -> list[Article]:
        """
        Scrapea todas las noticias del listado, las guarda en la base de datos
        y devuelve una lista de artículos procesados.
        """
        urls = self.parse_listing()
        if not urls:
            print("[⚠️ AVISO] No se encontraron artículos para procesar.")
            return []

        db = next(get_db())
        articulos_guardados = []
        saved_records = []

        for url in urls:
            article = self.parse_article(url)
            if not article:
                continue

            # ✅ DETECTAR CATEGORÍA AUTOMÁTICAMENTE
            categoria = self.detectar_categoria(
                article.titulo, 
                article.contenido, 
                article.fuente
            )
            logger.debug(f"🏷️  Categoría detectada: {categoria}")

            try:
                payload = {
                    "url": article.url,
                    "fuente": article.fuente,
                    "titulo": article.titulo,
                    "contenido": article.contenido,
                    "fecha_publicacion": article.fecha_publicacion,
                    "imagen_path": article.imagen_url,
                    "categoria": categoria  # ✅ AHORA CON CATEGORÍA
                }
                noticia_obj = upsert_noticia(db, payload)
                # Guardar resumen del registro persistido
                articulos_guardados.append(article)
                try:
                    saved_records.append({
                        "id": noticia_obj.id,
                        "titulo": noticia_obj.titulo,
                        "url": noticia_obj.url
                    })
                except Exception:
                    # En caso de objetos desconectados, usar el artículo extraído
                    saved_records.append({"id": None, "titulo": article.titulo, "url": article.url})
                logger.info(f"✅ Noticia guardada: {article.titulo[:80]}... | {article.url}")
            except Exception as e:
                logger.error(f"[❌ ERROR] No se pudo guardar la noticia {url}: {e}")
                # Log payload for debugging
                try:
                    logger.debug(f"Payload: {payload}")
                except Exception:
                    pass

        db.close()
        logger.info(f"🎯 Scrap finalizado. {len(articulos_guardados)} noticias guardadas o actualizadas.")
        # Devolver lista de resúmenes de noticias guardadas
        return saved_records