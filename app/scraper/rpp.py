# app/scraper/rpp.py
from __future__ import annotations
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import trafilatura

from app.scraper.base import BaseScraper, Article
from app.services.news_service import upsert_noticia
from app.database import get_db


class RPPScraper(BaseScraper):
    """Scraper específico para RPP (radiProgramas del Perú)"""
    
    def __init__(self, listado_url: str):
        super().__init__()
        self.listado_url = listado_url
        self.fuente = "rpp.pe"

    def parse_listing(self) -> list[str]:
        """Obtiene los enlaces de artículos desde la página de listado de RPP."""
        print(f"🔗 Analizando listado RPP: {self.listado_url}")
        try:
            html = self.fetch(self.listado_url)
        except Exception as e:
            print(f"[❌ ERROR] No se pudo obtener el listado de RPP {self.listado_url}: {e}")
            return []

        soup = BeautifulSoup(html, "html.parser")
        links = []

        # Selectores específicos de RPP para artículos
        article_selectors = [
            "a[href*='/noticias/']",
            "a[href*='/deportes/']", 
            "a[href*='/politica/']",
            "a[href*='/economia/']",
            "a[href*='/tecnologia/']",
            ".news-title a",
            ".story-item a",
            ".news-item a"
        ]

        for selector in article_selectors:
            for a in soup.select(selector):
                href = a.get('href')
                if href:
                    full_url = urljoin(self.listado_url, href)
                    if 'rpp.pe' in full_url and '/noticia_' in full_url:
                        clean_url = full_url.split('?')[0].split('#')[0]
                        if clean_url not in links:
                            links.append(clean_url)

        print(f"✅ Se encontraron {len(links)} artículos de RPP.")
        return links[:30]  # Límite para RPP

    def parse_article(self, url: str) -> Article | None:
        """Descarga y analiza un artículo individual de RPP."""
        print(f"📰 Extrayendo artículo RPP: {url}")
        try:
            html = self.fetch(url)
        except Exception as e:
            print(f"[⚠️ ERROR] No se pudo descargar el artículo RPP {url}: {e}")
            return None

        soup = BeautifulSoup(html, "html.parser")
        
        # Extraer título específico de RPP
        title_elem = soup.find('h1') or soup.find('title')
        title = title_elem.get_text().strip() if title_elem else "Sin título"
        
        # Extraer contenido con trafilatura
        extracted = trafilatura.extract(html, include_comments=False, include_tables=False)
        if not extracted:
            print(f"[⚠️ AVISO] No se pudo extraer contenido de {url}")
            return None

        # Extraer fecha de RPP
        fecha = None
        time_elem = soup.find('time')
        if time_elem and time_elem.get('datetime'):
            try:
                fecha = datetime.fromisoformat(time_elem['datetime'].replace('Z', '+00:00'))
            except:
                pass

        # Extraer imagen de RPP
        imagen = None
        img_elem = soup.find('meta', property='og:image')
        if img_elem:
            imagen = img_elem.get('content')

        return Article(
            url=url,
            fuente=self.fuente,
            titulo=title,
            contenido=extracted,
            fecha_publicacion=fecha,
            imagen_url=imagen,
        )

    def scrape_and_store(self) -> list[Article]:
        """
        Scrapea todas las noticias del listado de RPP, las guarda en la base de datos
        y devuelve una lista de artículos procesados.
        """
        urls = self.parse_listing()
        if not urls:
            print("[⚠️ AVISO] No se encontraron artículos de RPP para procesar.")
            return []

        db = next(get_db())
        articulos_guardados = []

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
            
            print(f"🏷️  Categoría detectada para RPP: {categoria}")

            try:
                upsert_noticia(db, {
                    "url": article.url,
                    "fuente": article.fuente,
                    "titulo": article.titulo,
                    "contenido": article.contenido,
                    "fecha_publicacion": article.fecha_publicacion,
                    "imagen_path": article.imagen_url,
                    "categoria": categoria  # ✅ CON CATEGORÍA
                })
                articulos_guardados.append(article)
                print(f"✅ Noticia RPP guardada: {article.titulo[:80]}...")
            except Exception as e:
                print(f"[❌ ERROR] No se pudo guardar la noticia RPP {url}: {e}")

        db.close()
        print(f"🎯 Scrap RPP finalizado. {len(articulos_guardados)} noticias guardadas.")
        return articulos_guardados