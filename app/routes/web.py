# app/routes/web.py (VERSIÓN COMPLETA ACTUALIZADA Y CORREGIDA)
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin, urlparse, urlencode
import logging
import json
import re
import asyncio

import requests
import trafilatura
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import desc, or_, func, distinct
from sqlalchemy.orm import Session
from sqlalchemy.sql.sqltypes import DateTime as SA_DateTime, Date as SA_Date

from app.models import Usuario, Fuente, Noticia
from app.auth import web_authenticate_user
from app.database import get_db
from app import models
from app.services.source_service import puede_agregar_fuente, contar_fuentes_usuario
from app.jobs.scheduler import scrapear_fuente_manual, scrapear_usuario_manual, run_trial_reminder_now
import json
import io
import csv
import pandas as pd
from fastapi.responses import StreamingResponse
from fastapi.responses import JSONResponse as FastJSONResponse
from sqlalchemy import inspect

# Helper: comprobar si request proviene de admin
def _request_is_admin(request: Request, db: Session) -> bool:
    # Primero, revisar session
    try:
        if request.session.get('is_admin'):
            return True
    except Exception:
        pass

    sess_email = None
    try:
        sess_email = request.session.get('user_email')
    except Exception:
        sess_email = None

    if sess_email == 'admin@nexnews.com':
        return True

    # Fallback: consultar DB por usuario con session email
    try:
        if sess_email:
            u = db.query(models.Usuario).filter(models.Usuario.email == sess_email).one_or_none()
            if u and getattr(u, 'is_admin', False):
                return True
    except Exception:
        pass

    # Último fallback: buscar cualquier usuario con is_admin True (if single admin exists)
    try:
        any_admin = db.query(models.Usuario).filter(models.Usuario.is_admin == True).first()
        if any_admin:
            # If current session user matches that admin
            if sess_email and sess_email == any_admin.email:
                return True
    except Exception:
        pass

    return False

router = APIRouter(prefix="/web", tags=["web"])
templates = Jinja2Templates(directory="app/web/templates")

logger = logging.getLogger("uvicorn")
USER_AGENT = "NewsMonitor/1.0 (+https://example.local)"


# =========================
# Normalización de categorías
# =========================

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

def _norm(s: str | None) -> str | None:
    if not s: return None
    return s.strip().lower()

def _normalize_category(raw: str | None) -> str | None:
    if not raw:
        return None
    key = _norm(raw)
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


# =========================
# Utilidades scraping / fechas
# =========================

_ISO_FRACTION_RE = re.compile(r"^(.*T\d{2}:\d{2}:\d{2})(\.\d+)?(.*)$")
_TZ_RE = re.compile(r"^(.*?)([+-]\d{2}):?(\d{2})$")

def _parse_dt(dt_str: str | None) -> datetime | None:
    """Parser ISO8601 tolerante: Z, espacios, fracciones cortas/largas, offsets sin colon."""
    if not dt_str:
        return None
    s = dt_str.strip()

    # Z -> +00:00 ; normaliza espacio a 'T'
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    s = s.replace(" ", "T")

    # +0000 / -0500 -> +00:00 / -05:00
    m = _TZ_RE.match(s)
    if m:
        s = m.group(1) + m.group(2) + ":" + m.group(3)

    # Normaliza fracción a 6 dígitos (microsegundos)
    m2 = _ISO_FRACTION_RE.match(s)
    if m2:
        frac = m2.group(2)
        if frac:
            digits = frac[1:]  # quita el punto
            if len(digits) > 6:
                digits = digits[:6]
            else:
                digits = digits.ljust(6, "0")
            s = m2.group(1) + "." + digits + m2.group(3)

    try:
        return datetime.fromisoformat(s)
    except Exception:
        logger.debug(f"[PARSE_DT] Falló fromisoformat para '{dt_str}' -> '{s}'")
        return None

def _infer_category_from_url(u: str) -> str | None:
    path = urlparse(u).path.strip("/")
    if not path:
        return None
    parts = [p for p in path.split("/") if p]
    if not parts:
        return None
    cand = parts[0]
    if cand in SECTION_SLUGS_GENERIC and len(parts) > 1:
        cand = parts[1]
    cat = _normalize_category(cand)
    return cat

def _extract_ld_json_items(soup: BeautifulSoup) -> list[dict]:
    items = []
    for s in soup.find_all("script", type=lambda t: t and "ld+json" in t):
        try:
            data = json.loads(s.string or "")
        except Exception:
            continue
        if isinstance(data, dict):
            items.append(data)
        elif isinstance(data, list):
            items.extend([d for d in data if isinstance(d, dict)])
    return items

def _infer_category_from_meta(soup: BeautifulSoup) -> str | None:
    m = soup.find("meta", property="article:section")
    if m and m.get("content"):
        cat = _normalize_category(m["content"])
        if cat:
            return cat
    for name in ("section", "category"):
        m = soup.find("meta", attrs={"name": name})
        if m and m.get("content"):
            cat = _normalize_category(m["content"])
            if cat:
                return cat
    for it in _extract_ld_json_items(soup):
        val = it.get("articleSection") or it.get("section")
        if isinstance(val, list) and val:
            cat = _normalize_category(val[0])
            if cat:
                return cat
        elif isinstance(val, str):
            cat = _normalize_category(val)
            if cat:
                return cat
    key = soup.find("meta", attrs={"name": "keywords"})
    if key and key.get("content"):
        for token in re.split(r"[,;|/]+", key["content"]):
            cat = _normalize_category(token)
            if cat in set(CATEGORY_ALIASES.values()):
                return cat
    return None

def _looks_like_article_url(u: str) -> bool:
    """
    Versión mejorada para detectar URLs de artículos
    """
    path = urlparse(u).path.strip("/")
    if not path:
        return False
        
    last_part = path.split("/")[-1]
    
    # EXCLUSIONES
    if "." in last_part:  # Archivos (pdf, jpg, etc.)
        return False
        
    exclude_parts = SECTION_SLUGS_GENERIC.union({
        "politicas-de-privacidad", "terminos-y-condiciones", "contacto",
        "nosotros", "about", "contact", "privacy", "terms", "login", 
        "register", "auth", "user", "profile", "search", "tag", "category"
    })
    
    if last_part in exclude_parts:
        return False
        
    # REGLAS DE INCLUSIÓN
    # 1. Tiene al menos 2 guiones (indicativo de título)
    if last_part.count("-") >= 2:
        return True
        
    # 2. Es lo suficientemente largo para ser un slug
    if len(last_part) >= 15:
        return True
        
    # 3. Está en una ruta profunda (ej: /noticias/politica/titulo-articulo)
    if path.count("/") >= 2:
        return True
        
    return False

def _extract_links(list_url: str, html: str, same_domain_only: bool = True, max_links: int = 60) -> list[str]:
    """
    VERSIÓN MEJORADA - Detección inteligente de artículos para Latina y otros sitios
    """
    soup = BeautifulSoup(html, "html.parser")
    links = []
    base_host = urlparse(list_url).netloc
    
    logger.info(f"[SCRAPER] 🔗 Analizando listado: {list_url}")
    
    # PATRONES ESPECÍFICOS PARA SITIOS COMUNES
    site_patterns = {
        "latina.pe": [
            "/noticias/", "/tendencias/", "/espectaculos/", "/deportes/", 
            "/tecnologia/", "/farandula/", "/actualidad/", "/politica/",
            "/entretenimiento/", "/series/", "/musica/"
        ],
        "rpp.pe": [
            "/noticias/", "/politica/", "/deportes/", "/tecnologia/",
            "/actualidad/", "/peru/", "/mundo/", "/economia/"
        ],
        "peru21.pe": [
            "/noticias/", "/actualidad/", "/deportes/", "/politica/",
            "/lima/", "/mundo/", "/espectaculos/", "/economia/"
        ],
        "trome.pe": [
            "/noticias/", "/actualidad/", "/deportes/", "/espectaculos/",
            "/tendencias/", "/virales/", "/futbol/"
        ]
    }
    
    # PALABRAS CLAVE QUE INDICAN ARTÍCULOS
    article_keywords = [
        "noticia", "noticias", "articulo", "artículo", "news", "story",
        "reportaje", "informe", "actualidad", "tendencia", "deporte",
        "politica", "espectaculo", "farandula", "tecnologia", "mundo",
        "entretenimiento", "musica", "cine", "series", "deportes", "futbol"
    ]
    
    # EXCLUSIONES - lo que NO son artículos
    exclude_patterns = [
        "politicas-de-privacidad", "terminos-y-condiciones", "contacto",
        "nosotros", "about", "contact", "privacy", "terms", "pdf", 
        "document", ".pdf", ".doc", ".docx", "login", "register",
        "facebook", "twitter", "instagram", "youtube", "whatsapp",
        "auth", "user", "profile", "search", "tag", "category", "archivo",
        "publicidad", "anuncio", "advertisement", "ads", "promocion",
        "_files", "/pdf/", "/document/", "/static/", "/assets/"
    ]
    
    for a in soup.find_all("a", href=True):
        href = a.get("href")
        if not href:
            continue
            
        full_url = urljoin(list_url, href)
        parsed = urlparse(full_url)
        
        # Validaciones básicas
        if parsed.scheme not in ("http", "https"):
            continue
        if same_domain_only and parsed.netloc and base_host and (parsed.netloc != base_host):
            continue
            
        path = parsed.path.strip("/").lower()
        full_url_lower = full_url.lower()
        
        # EXCLUSIONES ESTRICTAS
        if any(exclude in path for exclude in exclude_patterns):
            continue
        if any(exclude in full_url_lower for exclude in [".pdf", ".doc", ".docx", "/pdf/", "/document/"]):
            continue
            
        # 1. DETECCIÓN POR PATRONES ESPECÍFICOS DEL SITIO
        site_key = parsed.netloc.replace("www.", "")
        if site_key in site_patterns:
            if any(pattern in path for pattern in site_patterns[site_key]):
                links.append(full_url)
                continue
                
        # 2. DETECCIÓN POR PALABRAS CLAVE EN LA URL
        if any(keyword in path for keyword in article_keywords):
            links.append(full_url)
            continue
            
        # 3. DETECCIÓN POR ESTRUCTURA DE LA URL
        last_part = path.split("/")[-1] if "/" in path else path
        
        # Debe tener al menos 2 partes separadas por guiones
        if last_part.count("-") >= 2:
            # Y ser lo suficientemente largo
            if len(last_part) >= 15:
                links.append(full_url)
                continue
                
        # 4. DETECCIÓN POR PROFUNDIDAD DE RUTA
        if path.count("/") >= 2 and len(last_part) >= 10:
            links.append(full_url)
            continue

    # Eliminar duplicados
    seen = set()
    unique_links = []
    for link in links:
        if link not in seen:
            seen.add(link)
            unique_links.append(link)

    logger.info(f"✅ Se encontraron {len(unique_links)} posibles artículos.")
    return unique_links[:max_links]

def _is_article_html(html: str) -> tuple[bool, dict]:
    soup = BeautifulSoup(html, "html.parser")
    meta = {}

    og_type = soup.find("meta", property="og:type")
    if og_type and (og_type.get("content", "").lower() in ("article", "news", "newsarticle")):
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

    meta["categoria"] = _infer_category_from_meta(soup)

    ld_items = _extract_ld_json_items(soup)
    for it in ld_items:
        t = it.get("@type")
        tlist = []
        if isinstance(t, list):
            tlist = [x.lower() for x in t if isinstance(x, str)]
        elif isinstance(t, str):
            tlist = [t.lower()]
        if any(x in ("article", "newsarticle") for x in tlist):
            meta.setdefault("title", it.get("headline") or it.get("name"))
            meta.setdefault("date", it.get("datePublished") or it.get("dateCreated"))
            meta.setdefault("categoria", _normalize_category(it.get("articleSection")))
            img = it.get("image")
            if isinstance(img, dict):
                meta.setdefault("image", img.get("url"))
            elif isinstance(img, list) and img:
                meta.setdefault("image", img[0].get("url") if isinstance(img[0], dict) else img[0])

    has_article_tag = soup.find("article") is not None
    has_h1 = soup.find("h1") is not None
    is_article = ("og_type" in meta or ld_items or (has_article_tag and has_h1))
    return is_article, meta

def _scrape_article(url: str, html: str | None = None) -> dict | None:
    try:
        if html is None:
            resp = requests.get(url, timeout=25, headers={"User-Agent": USER_AGENT})
            if not resp.ok:
                logger.warning(f"[SCRAPER] ❌ Error {resp.status_code} en: {url}")
                return None
            html = resp.text

        is_article, meta = _is_article_html(html)
        if not is_article:
            logger.warning(f"[SCRAPER] ⚠️ No parece artículo: {url}")
            return None

        categoria = meta.get("categoria") or _infer_category_from_url(url)
        categoria = _normalize_category(categoria) if categoria else None

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
                    
                    logger.info(f"📰 Extrayendo artículo: {url}")
                    logger.info(f"✅ Noticia guardada: {titulo[:50]}...")
                    return {
                        "titulo": titulo,
                        "contenido": j.get("text"),
                        "fecha_publicacion": j.get("date") or j.get("published") or meta.get("date"),
                        "imagen_url": imagen,
                        "categoria": categoria,
                    }
                except json.JSONDecodeError as e:
                    logger.warning(f"[SCRAPER] ⚠️ JSON inválido, fallback a texto: {e}")
            else:
                logger.debug(f"[SCRAPER] trafilatura JSON vacío, fallback a texto")
        except Exception as e:
            logger.debug(f"[SCRAPER] Error en extracción JSON: {e}, fallback")

        # ===== FALLBACK: Plain text extraction =====
        text = trafilatura.extract(html)
        if not text:
            logger.warning(f"[SCRAPER] ⚠️ Sin texto tras fallback: {url}")
            return None

        soup = BeautifulSoup(html, "html.parser")
        title_tag = soup.find("title")
        title_txt = (meta.get("title") or (title_tag.get_text(strip=True) if title_tag else None))

        titulo = title_txt or url
        
        # Procesar imagen de meta - puede ser string o lista
        meta_image = meta.get("image")
        if isinstance(meta_image, list) and meta_image:
            meta_image = meta_image[0]
        if isinstance(meta_image, str):
            meta_image = meta_image.strip()
        
        logger.info(f"📰 Extrayendo artículo: {url}")
        logger.info(f"✅ Noticia guardada: {titulo[:50]}...")

        return {
            "titulo": titulo,
            "contenido": text,
            "fecha_publicacion": meta.get("date"),
            "imagen_url": meta_image,
            "categoria": categoria,
        }
    except Exception as e:
        logger.error(f"[SCRAPER] 💥 Error extrayendo {url}: {e}")
        return None


# =========================
# Helpers de modelo / tipos
# =========================

def _noticia_has_col(colname: str) -> bool:
    try:
        return hasattr(models.Noticia, "__table__") and colname in models.Noticia.__table__.c
    except Exception:
        return False

def _noticia_col_is_datetime(colname: str) -> bool:
    try:
        col = models.Noticia.__table__.c[colname]
        return isinstance(col.type, (SA_DateTime, SA_Date))
    except Exception:
        return False

def _noticia_col_is_tzaware(colname: str) -> bool:
    """True si la columna DateTime está declarada con timezone=True."""
    try:
        col = models.Noticia.__table__.c[colname]
        return isinstance(col.type, SA_DateTime) and bool(getattr(col.type, "timezone", False))
    except Exception:
        return False


# =========================
# UPSERT seguro (manejo de fecha)
# =========================

def _upsert_noticia(db: Session, fuente: models.Fuente, url: str, art: dict) -> bool:
    existing = db.query(models.Noticia).filter(models.Noticia.url == url).one_or_none()
    now = datetime.utcnow()
    changed = False

    has_categoria = _noticia_has_col("categoria")
    is_fecha_dt_col = _noticia_col_is_datetime("fecha_publicacion")
    fecha_tzaware_col = _noticia_col_is_tzaware("fecha_publicacion")

    raw_fecha = art.get("fecha_publicacion") if art else None
    fecha_dt = _parse_dt(raw_fecha) if isinstance(raw_fecha, str) else (raw_fecha if isinstance(raw_fecha, datetime) else None)

    # Si la columna es naive pero la fecha viene con tz, convértela a UTC naive
    if is_fecha_dt_col and not fecha_tzaware_col and isinstance(fecha_dt, datetime) and fecha_dt.tzinfo is not None:
        fecha_dt = fecha_dt.astimezone(timezone.utc).replace(tzinfo=None)

    if is_fecha_dt_col:
        fecha_value_insert = fecha_dt
        if raw_fecha and not fecha_dt:
            logger.warning(f"[UPSERT] No pude parsear fecha '{raw_fecha}' para {url}; guardo NULL en DateTime.")
    else:
        fecha_value_insert = raw_fecha or (fecha_dt.isoformat() if fecha_dt else None)

    if existing is None:
        try:
            kwargs = dict(
                url=url,
                fuente=fuente.nombre or urlparse(fuente.url_listado).netloc,
                titulo=(art.get("titulo") if art else None) or url,
                contenido=(art.get("contenido") if art else None) or "",
                fecha_publicacion=fecha_value_insert,
                imagen_path=(art.get("imagen_url") if art else None),
                created_at=now,
                updated_at=now,
            )
            if has_categoria:
                kwargs["categoria"] = art.get("categoria")

            n = models.Noticia(**kwargs)
            db.add(n)
            db.commit()
            logger.debug(f"[UPSERT] Creada: {url}")
            return True
        except Exception:
            db.rollback()
            logger.exception(f"[UPSERT] Error creando: {url}")
            return False
    else:
        try:
            if art:
                if art.get("titulo") and art["titulo"] != existing.titulo:
                    existing.titulo = art["titulo"]; changed = True
                if art.get("contenido") and art["contenido"] != existing.contenido:
                    existing.contenido = art["contenido"]; changed = True

                if is_fecha_dt_col:
                    if fecha_dt and fecha_dt != existing.fecha_publicacion:
                        existing.fecha_publicacion = fecha_dt; changed = True
                else:
                    new_text_date = raw_fecha or (fecha_dt.isoformat() if fecha_dt else None)
                    if new_text_date and new_text_date != existing.fecha_publicacion:
                        existing.fecha_publicacion = new_text_date; changed = True

                if art.get("imagen_url") and art["imagen_url"] != (existing.imagen_path or ""):
                    existing.imagen_path = art["imagen_url"]; changed = True

                if has_categoria and art.get("categoria") and getattr(existing, "categoria", None) != art["categoria"]:
                    existing.categoria = art["categoria"]; changed = True

            if changed:
                existing.updated_at = now
                db.commit()
                logger.debug(f"[UPSERT] Actualizada: {url}")
            return changed
        except Exception:
            db.rollback()
            logger.exception(f"[UPSERT] Error actualizando: {url}")
            return False


# =========================
# ✅ CORREGIDO: Función para obtener usuario por defecto
# =========================

def get_default_user(db: Session):
    """Obtiene el primer usuario de la base de datos (temporal)"""
    return db.query(Usuario).first()


# =========================
# Páginas: DASHBOARD
# =========================

@router.get("/dashboard")
async def dashboard(
    request: Request,
    db: Session = Depends(get_db)
):
    # ✅ TEMPORAL: Obtener usuario por defecto
    current_user = get_default_user(db)
    
    # Obtener estadísticas para el dashboard
    total_noticias = db.query(Noticia).count()
    total_fuentes = db.query(Fuente).count()
    fuentes_activas = db.query(Fuente).filter(Fuente.habilitada == True).count()
    
    # Obtener noticias recientes
    noticias_recientes = db.query(Noticia).order_by(desc(Noticia.created_at)).limit(5).all()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request, 
        "user": current_user,
        "total_noticias": total_noticias,
        "total_fuentes": total_fuentes,
        "fuentes_activas": fuentes_activas,
        "noticias_recientes": noticias_recientes
    })


# =========================
# SCRAPING - CORREGIDO (PARA CUALQUIER FUENTE)
# =========================

@router.post("/sources/{fuente_id}/scrape")
async def web_scrape_source(
    fuente_id: int, 
    request: Request, 
    db: Session = Depends(get_db),
):
    # ✅ CORREGIDO: Scrapear cualquier fuente
    fuente = db.query(models.Fuente).filter(models.Fuente.id == fuente_id).first()
    
    if not fuente:
        raise HTTPException(404, "Fuente no encontrada")

    try:
        # Usar el primer usuario para el scraping
        current_user = get_default_user(db)
        resultado = await scrapear_fuente_manual(current_user.id, fuente_id)
        
        if resultado:
            msg = f"✅ Fuente '{fuente.nombre}' scrapeada exitosamente"
        else:
            msg = f"❌ Error al scrapear la fuente"
            
        return RedirectResponse(url="/sources/?msg=" + urlencode({"msg": msg}), status_code=303)
        
    except Exception as e:
        logger.error(f"[SCRAPER] Error scrapeando fuente {fuente_id}: {e}")
        return RedirectResponse(url="/sources/?err=" + urlencode({"err": f"Error: {str(e)}"}), status_code=303)

# En web.py - ACTUALIZA ESTA RUTA
@router.post("/scrape-all")
async def web_scrape_all(
    request: Request, 
    db: Session = Depends(get_db),
):
    """Scrapea todas las fuentes habilitadas - VERSIÓN CORREGIDA"""
    try:
        # Usar el primer usuario para el scraping
        current_user = get_default_user(db)
        
        # ✅ CORREGIDO: Obtener fuentes habilitadas
        fuentes_habilitadas = db.query(models.Fuente).filter(
            models.Fuente.habilitada == True
        ).all()
        
        if not fuentes_habilitadas:
            return RedirectResponse(
                url="/sources/?err=No+hay+fuentes+habilitadas+para+scrapear",
                status_code=303,
            )
        
        # ✅ CORREGIDO: Ejecutar scraping de forma síncrona para ver resultados
        from app.jobs.scheduler import scrapear_fuente_manual
        resultados = []
        
        for fuente in fuentes_habilitadas:
            try:
                logger.info(f"🚀 Iniciando scraping de: {fuente.nombre}")
                resultado = await scrapear_fuente_manual(current_user.id, fuente.id)
                resultados.append({
                    "fuente": fuente.nombre,
                    "éxito": bool(resultado)
                })
            except Exception as e:
                logger.error(f"❌ Error scrapeando {fuente.nombre}: {e}")
                resultados.append({
                    "fuente": fuente.nombre,
                    "éxito": False,
                    "error": str(e)
                })
        
        # Contar resultados
        exitosos = sum(1 for r in resultados if r["éxito"])
        total = len(resultados)
        
        msg = f"✅ Scraping completado: {exitosos}/{total} fuentes procesadas"
        logger.info(f"[SCRAPER] {msg}")
        
        return RedirectResponse(url="/sources/?msg=" + urlencode({"msg": msg}), status_code=303)
        
    except Exception as e:
        logger.error(f"[SCRAPER] Error iniciando scraping: {e}")
        return RedirectResponse(url="/sources/?err=" + urlencode({"err": f"Error: {str(e)}"}), status_code=303)

# =========================
# Páginas: NOTICIAS - CORREGIDO (SIN FILTRO POR USUARIO)
# =========================

@router.get("/news", response_class=HTMLResponse)
def news_page(
    request: Request,
    q: str | None = None,
    fuente: str | None = None,
    categoria: str | None = None,
    db: Session = Depends(get_db),
):
    # ✅ TEMPORAL: Obtener usuario por defecto
    current_user = get_default_user(db)
    
    # ✅ CORREGIDO: Mostrar TODAS las noticias sin filtrar por usuario
    qry = db.query(models.Noticia)  # ← QUITAR el join y filtro por usuario
    
    if fuente:
        qry = qry.filter(models.Noticia.fuente.ilike(f"%{fuente}%"))
    if q:
        like = f"%{q}%"
        qry = qry.filter(or_(
            models.Noticia.titulo.ilike(like),
            models.Noticia.contenido.ilike(like),
        ))
    if categoria and _noticia_has_col("categoria"):
        qry = qry.filter(models.Noticia.categoria.ilike(f"%{categoria}%"))

    total = qry.count()
    
    # OBTENER TODAS LAS NOTICIAS SIN LIMITE
    rows = qry.order_by(desc(models.Noticia.created_at)).all()

    # Obtener las TOP N categorías por frecuencia (máx 10)
    categorias = []
    if _noticia_has_col("categoria"):
        try:
            top_n = 10
            cat_rows = (
                db.query(models.Noticia.categoria, func.count(models.Noticia.id).label("cnt"))
                .filter(models.Noticia.categoria.isnot(None))
                .group_by(models.Noticia.categoria)
                .order_by(desc(func.count(models.Noticia.id)))
                .limit(top_n)
                .all()
            )
            categorias = [c[0] for c in cat_rows if c[0] is not None]
            total_categorias = len(categorias)
        except Exception as e:
            logger.error(f"[WEB] Error obteniendo categorías: {e}")
            categorias = []
            total_categorias = 0

    return templates.TemplateResponse(
        "news_list.html",
        {
            "request": request,
            "rows": rows,
            "q": q,
            "fuente": fuente,
            "categoria": categoria,
            "categorias": categorias,
            "total_categorias": total_categorias,
            "total": total,
            "current_user": current_user,
        },
    )

@router.get("/news/{noticia_id}", response_class=HTMLResponse)
def news_detail(
    noticia_id: int, 
    request: Request, 
    db: Session = Depends(get_db),
):
    # ✅ CORREGIDO: Mostrar cualquier noticia (sin verificar usuario)
    n = db.query(models.Noticia).filter(models.Noticia.id == noticia_id).one_or_none()
    
    if not n:
        raise HTTPException(status_code=404, detail="Noticia no encontrada")

    cambios = []
    if hasattr(models, "CambioNoticia"):
        try:
            cambios = (db.query(models.CambioNoticia)
                        .filter(models.CambioNoticia.noticia_id == noticia_id)
                        .order_by(desc(models.CambioNoticia.detected_at))
                        .all())
        except Exception as e:
            logger.error(f"[WEB] Error consultando cambios de noticia {noticia_id}: {e}")
            cambios = []

    return templates.TemplateResponse(
        "detail.html",
        {
            "request": request, 
            "n": n, 
            "cambios": cambios,
            "current_user": get_default_user(db)
        },
    )


# =========================
# RUTAS DE AUTENTICACIÓN WEB - AGREGADAS
# =========================

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Página de login"""
    return templates.TemplateResponse("login.html", {
        "request": request,
        "current_user": None
    })

@router.post("/login")
async def web_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Procesar login web"""
    try:
        # Usar la autenticación web que valida hash y establece sesión
        user = await web_authenticate_user(request, email, password, db)
        if not user:
            return templates.TemplateResponse("login.html", {
                "request": request,
                "error": "Email o contraseña incorrectos",
                "current_user": None
            })

        # Asegurar claves de sesión relevantes
        try:
            request.session["user_id"] = user.id
            request.session["user_email"] = user.email
            request.session["user_plan"] = user.plan
            request.session["user_nombre"] = user.nombre
            request.session["is_admin"] = bool(getattr(user, 'is_admin', False))
            request.session["user_plan_trial_expires"] = user.plan_trial_expires.isoformat() if user.plan_trial_expires else None
        except Exception:
            pass

        response = RedirectResponse(url="/web/dashboard", status_code=303)
        return response
        
    except Exception as e:
        logger.error(f"Error en login: {e}")
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Error interno del servidor",
            "current_user": None
        })

@router.get("/logout")
async def web_logout(request: Request):
    """Cerrar sesión"""
    try:
        request.session.clear()
    except Exception:
        pass
    return RedirectResponse(url="/web/login", status_code=303)

@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Página de registro"""
    return templates.TemplateResponse("registro.html", {
        "request": request,
        "current_user": None
    })


# =========================
# OTRAS PÁGINAS WEB
# =========================

@router.get("/export", response_class=HTMLResponse)
async def export_page(request: Request, db: Session = Depends(get_db)):
    """Página de exportación de datos"""
    current_user = get_default_user(db)
    return templates.TemplateResponse("export.html", {
        "request": request,
        "current_user": current_user
    })

@router.get("/plans", response_class=HTMLResponse)
async def plans_page(request: Request, db: Session = Depends(get_db)):
    """Página de planes y precios"""
    current_user = get_default_user(db)
    return templates.TemplateResponse("plans.html", {
        "request": request,
        "current_user": current_user
    })


@router.post("/upgrade-plan")
async def upgrade_plan(request: Request, db: Session = Depends(get_db)):
    """Endpoint sencillo para actualizar el plan del usuario a 'premium'.
    - Si no hay usuario autenticado (temporal), devuelve `redirect` hacia el registro.
    - Si existe un usuario, actualiza sus campos de plan y límites y devuelve JSON.
    """
    try:
        current_user = get_default_user(db)
        if not current_user:
            # Indicar al cliente que redirija a registro/login
            return {"ok": False, "redirect": "/web/registro?plan=premium"}

        # Actualizar plan y límites y establecer trial de 14 días
        now = datetime.utcnow()
        current_user.plan = "premium"
        current_user.max_fuentes = None
        current_user.max_noticias_mes = None
        current_user.max_posts_social_mes = None
        current_user.plan_trial_start = now
        current_user.plan_trial_expires = now + timedelta(days=14)
        db.add(current_user)
        db.commit()

        # Si la petición viene desde la web con sesión, actualizar la sesión también
        try:
            request.session["user_plan"] = current_user.plan
            request.session["user_plan_trial_expires"] = current_user.plan_trial_expires.isoformat() if current_user.plan_trial_expires else None
        except Exception:
            pass

        # Registrar movimiento de auditoría: usuario se actualizó a premium
        try:
            # Prefer actor from session if available
            actor_id = None
            try:
                actor_id = request.session.get('user_id')
            except Exception:
                actor_id = None

            detalle = json.dumps({
                "user_id": current_user.id,
                "email": getattr(current_current:=current_user, 'email', None),
                "plan_trial_expires": current_current.plan_trial_expires.isoformat() if current_current.plan_trial_expires else None
            }, default=str)
            mov = models.Movimiento(actor_id=actor_id or current_user.id, accion='upgrade_plan', detalle=detalle)
            db.add(mov)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"[WEB] Error registrando movimiento upgrade_plan: {e}")

        return {"ok": True, "msg": "Plan actualizado a Premium (trial 14 días activado)"}

    except Exception as e:
        db.rollback()
        logger.exception(f"[WEB] Error actualizando plan: {e}")
        return {"ok": False, "msg": "Error interno al actualizar el plan"}

@router.get("/metrics", response_class=HTMLResponse)
async def metrics_page(request: Request, db: Session = Depends(get_db)):
    """Página de métricas"""
    current_user = get_default_user(db)
    return templates.TemplateResponse("metrics.html", {
        "request": request,
        "current_user": current_user
    })


@router.get("/admin/trials")
def admin_list_trials(request: Request, db: Session = Depends(get_db)):
    """Endpoint admin para listar trials activos y expirados (solo admin)."""
    try:
        # Verificar que el request provenga del admin (simple check)
        sess_email = None
        try:
            sess_email = request.session.get("user_email")
        except Exception:
            sess_email = None

        # Comprobar admin usando helper
        if not _request_is_admin(request, db):
            raise HTTPException(status_code=403, detail="Acceso restringido")

        rows = db.query(models.Usuario).filter(models.Usuario.plan == "premium").all()
        payload = [
            {
                "id": u.id,
                "email": u.email,
                "plan_trial_start": u.plan_trial_start.isoformat() if u.plan_trial_start else None,
                "plan_trial_expires": u.plan_trial_expires.isoformat() if u.plan_trial_expires else None,
                "plan_trial_reminder_sent": u.plan_trial_reminder_sent.isoformat() if u.plan_trial_reminder_sent else None,
            }
            for u in rows
        ]
        return JSONResponse({"ok": True, "trials": payload})
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[ADMIN] Error listando trials: {e}")
        raise HTTPException(status_code=500, detail="Error interno")


@router.get("/admin/movements", response_class=HTMLResponse)
def admin_movements_page(request: Request, db: Session = Depends(get_db)):
    """Página admin para ver movimientos y actividad del sistema (solo admin)."""
    try:
        sess_email = None
        try:
            sess_email = request.session.get("user_email")
        except Exception:
            sess_email = None

        if not _request_is_admin(request, db):
            raise HTTPException(status_code=403, detail="Acceso restringido")

        # Trials / usuarios premium
        premium_users = db.query(models.Usuario).filter(models.Usuario.plan == "premium").all()

        # Fuentes recientes
        recent_fuentes = db.query(models.Fuente).order_by(desc(models.Fuente.created_at)).limit(20).all()

        # Noticias recientes (movimientos de scraping)
        recent_noticias = db.query(models.Noticia).order_by(desc(models.Noticia.created_at)).limit(50).all()

        # Movimientos de auditoría (filtros + paginados)
        recent_movimientos = []
        # Filtros desde query params
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')
        actor_q = request.query_params.get('actor')
        accion_q = request.query_params.get('accion')

        page = int(request.query_params.get('page', 1) or 1)
        per_page = 20
        try:
            qry = db.query(models.Movimiento)

            # Fecha inicio
            if start_date_str:
                try:
                    sd = datetime.fromisoformat(start_date_str)
                    qry = qry.filter(models.Movimiento.created_at >= sd)
                except Exception:
                    pass

            # Fecha fin (incluir todo el día)
            if end_date_str:
                try:
                    ed = datetime.fromisoformat(end_date_str)
                    # añadir 1 día para incluir fecha completa
                    ed_inc = ed + timedelta(days=1)
                    qry = qry.filter(models.Movimiento.created_at < ed_inc)
                except Exception:
                    pass

            # Filtrar por accion
            if accion_q:
                qry = qry.filter(models.Movimiento.accion.ilike(f"%{accion_q}%"))

            # Filtrar por actor: si es numérico se compara por actor_id, si no se intenta join con Usuario.email
            if actor_q:
                if actor_q.isdigit():
                    qry = qry.filter(models.Movimiento.actor_id == int(actor_q))
                else:
                    qry = qry.join(models.Usuario, models.Usuario.id == models.Movimiento.actor_id, isouter=True)
                    qry = qry.filter(models.Usuario.email.ilike(f"%{actor_q}%"))

            total_movs = qry.with_entities(func.count(models.Movimiento.id)).scalar() or 0
            total_pages = max(1, (total_movs + per_page - 1) // per_page)
            offset = (page - 1) * per_page
            recent_movimientos = qry.order_by(desc(models.Movimiento.created_at)).offset(offset).limit(per_page).all()
        except Exception:
            # Si la tabla 'movimientos' no existe o hay otro error, no fallamos la vista completa
            recent_movimientos = []
            total_pages = 1
            page = 1

        return templates.TemplateResponse("admin_movements.html", {
            "request": request,
            "premium_users": premium_users,
            "recent_fuentes": recent_fuentes,
            "recent_noticias": recent_noticias,
            "recent_movimientos": recent_movimientos,
            "current_user": get_default_user(db),
            "movements_page": page,
            "movements_total_pages": total_pages,
            "movements_filters": {
                "start_date": start_date_str,
                "end_date": end_date_str,
                "actor": actor_q,
                "accion": accion_q,
            },
        })

    except HTTPException:
        raise
    except Exception as e:
        # Log detallado y devolver una vista amigable en vez de 500 crudo
        logger.exception(f"[ADMIN] Error rendering movements: {e}")
        msg = "Ocurrió un error al cargar la página admin. Revisa los logs del servidor para más detalles."
        return templates.TemplateResponse("admin_movements.html", {
            "request": request,
            "premium_users": [],
            "recent_fuentes": [],
            "recent_noticias": [],
            "recent_movimientos": [],
            "current_user": None,
            "movements_page": 1,
            "movements_total_pages": 1,
            "error": msg,
        })


@router.post("/admin/remind-trials")
async def admin_remind_trials(request: Request, db: Session = Depends(get_db)):
    """Endpoint admin para disparar recordatorios de trials inmediatamente."""
    try:
        sess_email = None
        try:
            sess_email = request.session.get("user_email")
        except Exception:
            sess_email = None

        if sess_email != "admin@nexnews.com":
            raise HTTPException(status_code=403, detail="Acceso restringido")

        # Ejecutar en hilo para no bloquear
        import asyncio
        result = await asyncio.to_thread(run_trial_reminder_now)

        # Registrar movimiento de auditoría
        try:
            # determinar actor desde session
            actor_id = None
            try:
                sess_email = request.session.get('user_email')
                if sess_email:
                    u = db.query(models.Usuario).filter(models.Usuario.email == sess_email).one_or_none()
                    if u:
                        actor_id = u.id
            except Exception:
                actor_id = None

            detalle = json.dumps({"summary": result}, default=str)
            mov = models.Movimiento(actor_id=actor_id,
                                    accion='remind_trials',
                                    detalle=detalle)
            db.add(mov)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"[ADMIN] Error registrando movimiento: {e}")

        return JSONResponse({"ok": True, "result": result})
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[ADMIN] Error triggering reminders: {e}")
        raise HTTPException(status_code=500, detail="Error interno")

@router.get("/payments", response_class=HTMLResponse)
async def payments_page(request: Request, db: Session = Depends(get_db)):
    """Página de pagos"""
    current_user = get_default_user(db)
    return templates.TemplateResponse("payments.html", {
        "request": request,
        "current_user": current_user
    })


# =========================
# RUTA TEMPORAL PARA DIAGNÓSTICO
# =========================

@router.get("/debug")
def debug_info(db: Session = Depends(get_db)):
    """Ruta temporal para ver qué hay en la base de datos"""
    usuarios = db.query(Usuario).all()
    fuentes = db.query(Fuente).all()
    noticias = db.query(Noticia).count()
    
    resultado = {
        "usuarios": [
            {"id": u.id, "email": u.email, "plan": u.plan, "activo": u.activo} 
            for u in usuarios
        ],
        "total_fuentes": len(fuentes),
        "fuentes": [
            {"id": f.id, "nombre": f.nombre, "url": f.url_listado, "usuario_id": f.usuario_id, "habilitada": f.habilitada}
            for f in fuentes
        ],
        "total_noticias": noticias
    }
    
    return resultado