# app/scraper/base.py
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any
import time
import logging

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from sqlalchemy.orm import Session

from app.config import settings

log = logging.getLogger(__name__)


@dataclass
class Article:
    url: str
    fuente: str
    titulo: str
    contenido: str
    fecha_publicacion: Optional[datetime]
    imagen_url: Optional[str]


class BaseScraper:
    """Base class for scrapers.

    Provides a requests.Session with retries, simple rate limiting and
    a small helper `fetch` used by concrete scrapers.
    """

    fuente: str = "base"

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()

        retries = Retry(
            total=getattr(settings, "REQUEST_RETRIES", 3),
            backoff_factor=getattr(settings, "BACKOFF_FACTOR", 0.5),
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE", "HEAD"],
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self.user_agent = getattr(settings, "USER_AGENT", "news-scraper/1.0")
        self.timeout = getattr(settings, "REQUEST_TIMEOUT", 15)
        self.rate_limit = getattr(settings, "RATE_LIMIT_SECONDS", 0)

        # timestamp of last request (for simple rate limiting)
        self._last_request_at = 0.0

    def _sleep_rate_limit(self) -> None:
        if not self.rate_limit:
            return
        elapsed = time.time() - self._last_request_at
        if elapsed < self.rate_limit:
            to_sleep = self.rate_limit - elapsed
            log.debug("Rate limit: sleeping %.2fs", to_sleep)
            time.sleep(to_sleep)

    def fetch(self, url: str, params: Optional[dict[str, Any]] = None, headers: Optional[dict[str, str]] = None,
              timeout: Optional[float] = None, allow_redirects: bool = True, proxies: Optional[dict] = None) -> str:
        """Fetch a URL and return text. Raises on HTTP errors.

        Uses session with retries. Honors rate limit configured in settings.
        """
        headers = dict(headers or {})
        headers.setdefault("User-Agent", self.user_agent)

        self._sleep_rate_limit()
        try:
            resp = self.session.get(url, params=params, headers=headers, timeout=timeout or self.timeout,
                                    allow_redirects=allow_redirects, proxies=proxies)
            self._last_request_at = time.time()
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            log.exception("Error fetching %s: %s", url, exc)
            raise

    # ✅ NUEVO MÉTODO PARA DETECTAR CATEGORÍAS
    def detectar_categoria(self, titulo: str, contenido: str, fuente: str) -> str:
        """Detecta la categoría de una noticia basada en palabras clave."""
        texto = f"{titulo.lower()} {contenido.lower()}"
        
        categorias_keywords = {
            "Deportes": ["fútbol", "deporte", "partido", "liga", "madrid", "vallecano", 
                        "jugador", "equipo", "campeonato", "gol", "atleta", "deportivo",
                        "tenis", "baloncesto", "natación", "olímpico", "estadio"],
            "Política": ["gobierno", "presidente", "política", "ministro", "congreso",
                        "elecciones", "partido político", "ley", "reforma", "estado",
                        "parlamento", "senado", "democracia", "votación", "mandatario"],
            "Economía": ["dólar", "precio", "economía", "mercado", "finanzas", "bolsa",
                        "inflación", "empresa", "negocios", "comercio", "dinero",
                        "inversión", "banco", "empleo", "pib", "crecimiento"],
            "Tecnología": ["tecnología", "digital", "internet", "app", "software", 
                          "hardware", "innovación", "ciencia", "investigación", "robot",
                          "inteligencia artificial", "redes sociales", "smartphone"],
            "Salud": ["salud", "médico", "hospital", "enfermedad", "vacuna", "covid",
                     "tratamiento", "paciente", "medicina", "salud pública", "virus",
                     "epidemia", "médico", "cirugía", "farmacia"]
        }
        
        for categoria, keywords in categorias_keywords.items():
            if any(keyword in texto for keyword in keywords):
                return categoria
        
        return "General"

    # ✅ NUEVO MÉTODO PARA VERIFICAR LÍMITES DE USUARIO
    def verificar_limite_fuentes_usuario(self, db: Session, usuario_id: int, fuente_id: int) -> bool:
        """Verifica si un usuario puede scrapear una fuente específica según su plan."""
        from app.models import Usuario, Fuente
        
        usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
        if not usuario:
            log.error(f"Usuario {usuario_id} no encontrado")
            return False
        
        # Usuarios premium pueden scrapear todas las fuentes
        if usuario.plan == "premium":
            return True
        
        # Para usuarios gratis: obtener sus primeras X fuentes (ordenadas por ID)
        max_fuentes = usuario.max_fuentes or 3  # Default a 3 si no está definido
        
        fuentes_permitidas = db.query(Fuente).filter(
            Fuente.usuario_id == usuario_id,
            Fuente.habilitada == True
        ).order_by(Fuente.id).limit(max_fuentes).all()
        
        # Verificar si la fuente está entre las permitidas
        fuente_permitida = any(fuente.id == fuente_id for fuente in fuentes_permitidas)
        
        if not fuente_permitida:
            log.warning(f"Usuario {usuario_id} (plan {usuario.plan}) intentó scrapear fuente {fuente_id} no permitida")
            log.warning(f"Fuentes permitidas: {[f.id for f in fuentes_permitidas]}")
        
        return fuente_permitida

    # ✅ NUEVO MÉTODO PARA OBTENER FUENTES PERMITIDAS
    def obtener_fuentes_permitidas(self, db: Session, usuario_id: int):
        """Obtiene las fuentes que un usuario puede scrapear según su plan."""
        from app.models import Usuario, Fuente
        
        usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
        if not usuario:
            return []
        
        query = db.query(Fuente).filter(
            Fuente.usuario_id == usuario_id,
            Fuente.habilitada == True
        )
        
        # Para usuarios gratis, limitar a las primeras X fuentes
        if usuario.plan == "gratis":
            max_fuentes = usuario.max_fuentes or 3
            query = query.order_by(Fuente.id).limit(max_fuentes)
        
        return query.all()

    # ✅ NUEVO MÉTODO PARA SCRAPEAR CON LÍMITES
    async def scrapear_fuentes_usuario(self, db: Session, usuario_id: int):
        """Scrapea solo las fuentes permitidas para el usuario."""
        from app.models import Fuente
        
        fuentes_permitidas = self.obtener_fuentes_permitidas(db, usuario_id)
        
        if not fuentes_permitidas:
            log.warning(f"Usuario {usuario_id} no tiene fuentes permitidas para scrapear")
            return
        
        usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
        plan_info = "Premium" if usuario.plan == "premium" else f"Gratis ({len(fuentes_permitidas)}/{usuario.max_fuentes or 3} fuentes)"
        
        log.info(f"🔍 Scrapeando para usuario {usuario_id} ({plan_info}): {len(fuentes_permitidas)} fuentes")
        
        for fuente in fuentes_permitidas:
            try:
                if await self.scrape_fuente(fuente, db):
                    log.info(f"✅ Scrapeada: {fuente.nombre}")
                else:
                    log.warning(f"❌ Falló scraping: {fuente.nombre}")
            except Exception as e:
                log.error(f"💥 Error scrapeando {fuente.nombre}: {e}")

    # ✅ NUEVO MÉTODO PARA SCRAPEAR FUENTE ESPECÍFICA CON VERIFICACIÓN
    async def scrape_fuente_con_verificacion(self, db: Session, usuario_id: int, fuente_id: int) -> bool:
        """Scrapea una fuente específica solo si el usuario tiene permiso."""
        from app.models import Fuente
        
        # Verificar límites primero
        if not self.verificar_limite_fuentes_usuario(db, usuario_id, fuente_id):
            log.error(f"Usuario {usuario_id} no tiene permiso para scrapear fuente {fuente_id}")
            return False
        
        fuente = db.query(Fuente).filter(Fuente.id == fuente_id).first()
        if not fuente:
            log.error(f"Fuente {fuente_id} no encontrada")
            return False
        
        try:
            resultado = await self.scrape_fuente(fuente, db)
            if resultado:
                log.info(f"✅ Fuente scrapeada exitosamente: {fuente.nombre}")
            return resultado
        except Exception as e:
            log.error(f"💥 Error scrapeando fuente {fuente.nombre}: {e}")
            return False

    # ✅ MÉTODO AUXILIAR PARA SCRAPEAR FUENTE (debe ser implementado por scrapers específicos)
    async def scrape_fuente(self, fuente, db: Session) -> bool:
        """Scrapea una fuente específica y guarda los resultados en la base de datos."""
        # Este método debe ser implementado por cada scraper concreto
        # Debe retornar True si fue exitoso, False si falló
        raise NotImplementedError("Cada scraper debe implementar este método")

    # Concrete scrapers should implement the following
    def parse_listing(self, html: str) -> list[str]:
        """Return list of article URLs from a listing page."""
        raise NotImplementedError

    def parse_article(self, html: str, url: str) -> Article:
        """Parse a single article page and return an Article instance."""
        raise NotImplementedError