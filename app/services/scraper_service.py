"""
Servicio centralizado de scraping y extracción de noticias.
Consolida toda la lógica de scraping para evitar duplicación.
"""

from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
import logging
import json
import re

import requests
import trafilatura
from bs4 import BeautifulSoup

logger = logging.getLogger("uvicorn")
USER_AGENT = "NewsMonitor/1.0 (+https://example.local)"

# Normalización de categorías
CATEGORY_ALIASES = {
    "politica": "Política",
    "política": "Política",
    "gobierno": "Política",
    "congreso": "Política",
    "judiciales": "Judiciales",
    "justicia": "Judiciales",
    "deportes": "Deportes",
    "deporte": "Deportes",
    "futbol": "Deportes",
    "fútbol": "Deportes",
    "economia": "Economía",
    "economía": "Economía",
    "negocios": "Economía",
    "finanzas": "Economía",
    "tecnologia": "Tecnología",
    "tecnología": "Tecnología",
    "tecno": "Tecnología",
    "ciencia": "Ciencia",
    "salud": "Salud",
    "vital": "Salud",
    "peru": "Perú",
    "méxico": "México",
    "mundo": "Mundo",
    "internacional": "Mundo",
    "lima": "Lima",
    "policiales": "Policiales",
    "seguridad": "Policiales",
    "entretenimiento": "Entretenimiento",
    "espectaculos": "Entretenimiento",
    "espectáculos": "Entretenimiento",
    "videojuegos": "Videojuegos",
    "opinion": "Opinión",
    "opinión": "Opinión",
}

SECTION_SLUGS_GENERIC = {
    "", "home", "inicio", "ultimas-noticias", "últimas-noticias", "portada", "principal",
    "buscar", "videos", "audio", "podcast", "programas"
}


def normalize_category(raw: str | None) -> str | None:
    """Normaliza categoría a valores estándar."""
    if not raw:
        return None
    key = raw.strip().lower()
    if not key:
        return None
    key = re.sub(r"[^a-záéíóúüñ0-9\s-]", "", key)
    key = key.replace("_", " ").strip()
    if key in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[key]
    for tok in re.split(r"[/\s\-|,;:]+", key):
        t = tok.strip()
        if t in CATEGORY_ALIASES:
            return CATEGORY_ALIASES[t]
    return raw.strip().capitalize()


# Lista permitida de categorías (solo estos valores serán usados a partir de ahora)
ALLOWED_CATEGORIES = {
    'Política', 'Deportes', 'Salud', 'Economía', 'Música',
    'Tecnología', 'Entretenimiento', 'Videojuegos', 'Tendencias'
}


def map_to_allowed_category(cat: str | None) -> str | None:
    """Garantiza que la categoría pertenezca a ALLOWED_CATEGORIES.
    Si `cat` es None o no está en la lista permitida, devuelve 'Tendencias'."""
    if not cat:
        return 'Tendencias'
    c = cat.strip()
    if c in ALLOWED_CATEGORIES:
        return c
    # Intentar coincidencia case-insensitive
    for a in ALLOWED_CATEGORIES:
        if a.lower() == c.lower():
            return a
    # No hay coincidencia razonable -> asignar 'Tendencias'
    return 'Tendencias'


def parse_iso_date(dt_str: str | None) -> datetime | None:
    """Parser ISO8601 tolerante: Z, espacios, fracciones, offsets."""
    if not dt_str:
        return None
    s = dt_str.strip()

    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    s = s.replace(" ", "T")

    # Normalizar offsets de zona horaria
    tz_match = re.match(r"^(.*?)([+-]\d{2}):?(\d{2})$", s)
    if tz_match:
        s = tz_match.group(1) + tz_match.group(2) + ":" + tz_match.group(3)

    # Normalizar fracciones
    frac_match = re.match(r"^(.*T\d{2}:\d{2}:\d{2})(\.\d+)?(.*)$", s)
    if frac_match and frac_match.group(2):
        digits = frac_match.group(2)[1:]
        if len(digits) > 6:
            digits = digits[:6]
        else:
            digits = digits.ljust(6, "0")
        s = frac_match.group(1) + "." + digits + frac_match.group(3)

    try:
        return datetime.fromisoformat(s)
    except Exception:
        logger.debug(f"No se pudo parsear fecha: {dt_str}")
        return None


def infer_category_from_url(url: str) -> str | None:
    """Infiere categoría desde la URL."""
    path = urlparse(url).path.strip("/")
    if not path:
        return None
    parts = [p for p in path.split("/") if p]
    if not parts:
        return None
    cand = parts[0]
    if cand in SECTION_SLUGS_GENERIC and len(parts) > 1:
        cand = parts[1]
    return normalize_category(cand)


def extract_ld_json(soup: BeautifulSoup) -> list[dict]:
    """Extrae items de LD+JSON del HTML."""
    items = []
    for script in soup.find_all("script", type=lambda t: t and "ld+json" in t):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, dict):
                items.append(data)
            elif isinstance(data, list):
                items.extend([d for d in data if isinstance(d, dict)])
        except Exception:
            pass
    return items


def infer_category_from_meta(soup: BeautifulSoup) -> str | None:
    """Infiere categoría desde meta tags y LD+JSON."""
    # Meta tags
    for meta in soup.find_all("meta"):
        if meta.get("property") == "article:section" or meta.get("name") in ("section", "category"):
            content = meta.get("content")
            if content:
                cat = normalize_category(content)
                if cat:
                    return map_to_allowed_category(cat)

    # LD+JSON
    for item in extract_ld_json(soup):
        val = item.get("articleSection") or item.get("section")
        if isinstance(val, list) and val:
            cat = normalize_category(val[0])
            if cat:
                return map_to_allowed_category(cat)
        elif isinstance(val, str):
            cat = normalize_category(val)
            if cat:
                return map_to_allowed_category(cat)

    # Keywords
    keywords = soup.find("meta", attrs={"name": "keywords"})
    if keywords and keywords.get("content"):
        for token in re.split(r"[,;|/]+", keywords["content"]):
            cat = normalize_category(token)
            if cat in set(CATEGORY_ALIASES.values()):
                return map_to_allowed_category(cat)

    return None


def scrape_article(url: str, html: str | None = None) -> dict | None:
    """
    Extrae información de un artículo.
    
    Returns:
        Dict con: titulo, contenido, fecha_publicacion, imagen_url, categoria
    """
    try:
        if html is None:
            resp = requests.get(url, timeout=25, headers={"User-Agent": USER_AGENT})
            if not resp.ok:
                logger.warning(f"Error {resp.status_code} en: {url}")
                return None
            html = resp.text

        soup = BeautifulSoup(html, "html.parser")
        
        # Extraer metadatos
        meta = {}
        og_type = soup.find("meta", property="og:type")
        if og_type and og_type.get("content", "").lower() in ("article", "news", "newsarticle"):
            meta["og_type"] = og_type.get("content")

        og_title = soup.find("meta", property="og:title")
        if og_title and og_title.get("content"):
            meta["title"] = og_title["content"].strip()

        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            meta["image"] = og_img["content"].strip()

        pub = soup.find("meta", property="article:published_time") or soup.find("meta", attrs={"name": "pubdate"})
        if pub and pub.get("content"):
            meta["date"] = pub["content"].strip()

        meta["categoria"] = infer_category_from_meta(soup)

        # Validar que es artículo
        ld_items = extract_ld_json(soup)
        has_article_tag = soup.find("article") is not None
        has_h1 = soup.find("h1") is not None
        is_article = ("og_type" in meta or ld_items or (has_article_tag and has_h1))

        if not is_article:
            logger.warning(f"No parece artículo: {url}")
            return None

        categoria = meta.get("categoria") or infer_category_from_url(url)
        categoria = normalize_category(categoria) if categoria else None
        # Asegurar que la categoría final pertenezca a las permitidas
        categoria = map_to_allowed_category(categoria)

        # ===== INTENTO 1: JSON extraction =====
        try:
            data = trafilatura.extract(html, output="json", include_images=True)
            
            # Validación estricta: data debe ser string no vacío
            if data and isinstance(data, str) and data.strip():
                try:
                    j = json.loads(data)
                    titulo = j.get("title") or meta.get("title") or "Sin título"
                    
                    # Procesar imagen - puede ser string o lista
                    imagen = j.get("image")
                    if isinstance(imagen, list) and imagen:
                        imagen = imagen[0]
                    if not imagen and j.get("images"):
                        images_list = j.get("images")
                        if isinstance(images_list, list) and images_list:
                            imagen = images_list[0]
                    if not imagen:
                        imagen = meta.get("image")
                    if isinstance(imagen, list) and imagen:
                        imagen = imagen[0]
                    if isinstance(imagen, str):
                        imagen = imagen.strip()
                    
                    logger.info(f"Extrayendo: {titulo[:50]}...")
                    return {
                        "titulo": titulo,
                        "contenido": j.get("text"),
                        "fecha_publicacion": j.get("date") or j.get("published") or meta.get("date"),
                        "imagen_url": imagen,
                        "categoria": categoria,
                    }
                except json.JSONDecodeError as e:
                    logger.debug(f"JSON inválido, fallback a texto: {e}")
            else:
                logger.debug(f"trafilatura JSON vacío, fallback a texto")
        except Exception as e:
            logger.debug(f"Error en extracción JSON: {e}, fallback")

        # ===== FALLBACK: Plain text extraction =====
        text = trafilatura.extract(html)
        if not text:
            logger.warning(f"Sin contenido tras fallback: {url}")
            return None

        title_tag = soup.find("title")
        titulo = meta.get("title") or (title_tag.get_text(strip=True) if title_tag else None) or url

        # Procesar imagen de meta - puede ser string o lista
        meta_image = meta.get("image")
        if isinstance(meta_image, list) and meta_image:
            meta_image = meta_image[0]
        if isinstance(meta_image, str):
            meta_image = meta_image.strip()

        logger.info(f"Extrayendo: {titulo[:50]}...")
        return {
            "titulo": titulo,
            "contenido": text,
            "fecha_publicacion": meta.get("date"),
            "imagen_url": meta_image,
            "categoria": categoria,
        }

    except Exception as e:
        logger.error(f"Error extrayendo {url}: {e}")
        return None
