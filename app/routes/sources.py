# app/routes/sources.py - VERSIÓN COMPLETA Y FUNCIONAL
from fastapi import APIRouter, Request, Form, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from datetime import datetime
from sqlalchemy.orm import Session
from urllib.parse import urlencode, urlparse
import logging
import asyncio

from app.database import get_db, create_default_user
from app import models
from app.models import Usuario, Fuente
from app.scraper.generic import GenericScraper
from app.services.source_service import add_fuente as svc_add_fuente

router = APIRouter(prefix="/sources", tags=["Fuentes"])
logger = logging.getLogger("uvicorn")

# ✅ Configurar templates
templates = Jinja2Templates(directory="app/web/templates")

# ✅ FUNCIÓN TEMPORAL: Obtener usuario por defecto
def get_default_user(db: Session):
    """Obtiene el primer usuario de la base de datos (temporal)"""
    return db.query(Usuario).first()

# ✅ FUNCIÓN DE SCRAPING REAL
async def ejecutar_scraping_fuente(fuente_id: int, db: Session) -> list:
    """Ejecuta el scraping real para una fuente.
    Devuelve una lista de diccionarios con los artículos guardados: [{id,titulo,url}, ...].
    """
    try:
        logger.info(f"🎯 Iniciando scraping REAL para fuente ID: {fuente_id}")
        
        # Obtener la fuente
        fuente = db.query(models.Fuente).filter(models.Fuente.id == fuente_id).first()
        if not fuente:
            logger.error(f"❌ Fuente {fuente_id} no encontrada")
            return False
        
        logger.info(f"📰 Scrapeando: {fuente.nombre} - {fuente.url_listado}")
        
        # Usar el scraper genérico ya implementado que maneja extracción y guardado
        try:
            # Ejecutar el scraping en un hilo separado para no bloquear el event loop
            def _run_scraper():
                s = GenericScraper(fuente.url_listado)
                return s.scrape_and_store()

            saved_articles = await asyncio.to_thread(_run_scraper)

            # saved_articles es una lista de dicts {id,titulo,url}
            saved_count = len(saved_articles) if isinstance(saved_articles, (list, tuple)) else 0

            # Actualizar última fecha de scraping si hubo resultados
            if saved_count > 0:
                fuente.last_scraped_at = datetime.now()
                fuente.updated_at = datetime.now()
                try:
                    db.commit()
                except Exception:
                    db.rollback()
            return saved_articles or []
        except Exception as e:
            logger.error(f"❌ Error ejecutando GenericScraper para fuente {fuente.id}: {e}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error en scraping para fuente {fuente_id}: {e}")
        return False

@router.post("/scrape-all")
async def scrapear_todas_fuentes(
    request: Request,
    db: Session = Depends(get_db)
):
    """Scrapea TODAS las fuentes habilitadas - VERSIÓN FUNCIONAL"""
    try:
        current_user = get_default_user(db)
        user_label = current_user.email if current_user else "<sistema>"
        logger.info(f"🚀 USUARIO: {user_label} iniciando scraping masivo")
        
        # Obtener todas las fuentes habilitadas
        fuentes = db.query(models.Fuente).filter(
            models.Fuente.habilitada == True
        ).all()
        
        if not fuentes:
            logger.warning("⚠️ No hay fuentes habilitadas para scrapear")
            return RedirectResponse(
                url="/sources/?err=No+hay+fuentes+habilitadas+para+scrapear",
                status_code=303,
            )
        
        logger.info(f"🎯 Iniciando scraping de {len(fuentes)} fuentes habilitadas...")
        
        resultados = []
        fuentes_procesadas = 0
        
        for fuente in fuentes:
            try:
                logger.info(f"🔍 Procesando fuente {fuentes_procesadas + 1}/{len(fuentes)}: {fuente.nombre}")
                
                # Ejecutar scraping REAL -> devuelve lista de artículos guardados
                saved_articles = await ejecutar_scraping_fuente(fuente.id, db)
                saved_count = len(saved_articles) if isinstance(saved_articles, (list, tuple)) else 0
                if saved_count > 0:
                    resultados.append(f"✅ {fuente.nombre} (+{saved_count} noticias)")
                    fuentes_procesadas += 1
                else:
                    resultados.append(f"❌ {fuente.nombre} (0 noticias)")
                    
                # Pequeña pausa entre fuentes
                await asyncio.sleep(1)
                    
            except Exception as e:
                error_msg = f"❌ {fuente.nombre}: Error - {str(e)}"
                resultados.append(error_msg)
                logger.error(error_msg)
        
        # Crear mensaje de resultado
        if fuentes_procesadas > 0:
            mensaje = f"Scraping completado: {fuentes_procesadas}/{len(fuentes)} fuentes procesadas exitosamente"
            logger.info(f"📊 {mensaje}")
            
            return RedirectResponse(
                url=f"/sources/?msg={urlencode({'msg': mensaje})}",
                status_code=303,
            )
        else:
            mensaje = "Scraping completado pero ninguna fuente pudo ser procesada"
            logger.warning(f"⚠️ {mensaje}")
            
            return RedirectResponse(
                url=f"/sources/?err={urlencode({'err': mensaje})}",
                status_code=303,
            )
        
    except Exception as e:
        logger.error(f"💥 ERROR CRÍTICO en scrapear_todas_fuentes: {e}")
        return RedirectResponse(
            url="/sources/?err=Error+crítico+al+iniciar+scraping+masivo",
            status_code=303,
        )

@router.post("/{fuente_id}/scrape")
async def scrapear_fuente_individual(
    fuente_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """Scrapea una fuente específica - VERSIÓN FUNCIONAL"""
    try:
        current_user = get_default_user(db)
        user_label = current_user.email if current_user else "<sistema>"
        logger.info(f"🎯 Usuario {user_label} scrapeando fuente individual ID: {fuente_id}")
        
        fuente = db.query(models.Fuente).filter(models.Fuente.id == fuente_id).first()
        
        if not fuente:
            logger.error(f"❌ Fuente {fuente_id} no encontrada")
            return RedirectResponse(
                url="/sources/?err=Fuente+no+encontrada",
                status_code=303,
            )

        # Verificar si la fuente está habilitada
        if not fuente.habilitada:
            logger.warning(f"⚠️ Fuente {fuente.nombre} está deshabilitada")
            return RedirectResponse(
                url="/sources/?err=La+fuente+está+deshabilitada",
                status_code=303,
            )

        # Ejecutar scraping REAL -> devuelve lista de artículos guardados
        saved_articles = await ejecutar_scraping_fuente(fuente_id, db)
        saved_count = len(saved_articles) if isinstance(saved_articles, (list, tuple)) else 0

        if saved_count > 0:
            mensaje = f"Scraping exitoso para {fuente.nombre}: {saved_count} noticias guardadas"
            logger.info(f"✅ {mensaje}")
            return RedirectResponse(
                url=f"/sources/?msg={urlencode({'msg': mensaje})}",
                status_code=303,
            )
        else:
            mensaje = f"Scraping completado para {fuente.nombre}: 0 noticias guardadas"
            logger.warning(f"⚠️ {mensaje}")
            return RedirectResponse(
                url=f"/sources/?err={urlencode({'err': mensaje})}",
                status_code=303,
            )
            
    except Exception as e:
        logger.error(f"💥 Error en scrapear_fuente_individual: {e}")
        return RedirectResponse(
            url="/sources/?err=Error+al+iniciar+scraping+individual",
            status_code=303,
        )

@router.get("/", response_class=HTMLResponse)
async def listar_fuentes(
    request: Request,
    q: str = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Lista TODAS las fuentes con paginación y búsqueda"""
    try:
        current_user = get_default_user(db)
        
        # MOSTRAR TODAS LAS FUENTES
        query = db.query(models.Fuente)
        
        if q:
            query = query.filter(
                (models.Fuente.nombre.ilike(f"%{q}%")) |
                (models.Fuente.url_listado.ilike(f"%{q}%"))
            )

        total = query.count()
        fuentes = query.order_by(models.Fuente.id.desc()).offset(offset).limit(limit).all()
        has_next = offset + limit < total

        # Calcular límites
        es_premium = current_user.plan == "premium" if current_user else False
        max_fuentes = None if es_premium else 3

        # DEBUG: Log para verificar fuentes
        logger.info(f"🔍 [FUENTES] Se encontraron {len(fuentes)} fuentes")

        return templates.TemplateResponse(
            "sources.html",
            {
                "request": request,
                "fuentes": fuentes,
                "total": total,
                "q": q,
                "limit": limit,
                "offset": offset,
                "has_next": has_next,
                "current_user": current_user,
                "es_premium": es_premium,
                "max_fuentes": max_fuentes,
                "fuentes_actuales": len(fuentes)
            },
        )
    except Exception as e:
        logger.error(f"❌ Error en listar_fuentes: {e}")
        return templates.TemplateResponse(
            "sources.html",
            {
                "request": request,
                "fuentes": [],
                "total": 0,
                "q": q,
                "limit": limit,
                "offset": offset,
                "has_next": False,
                "current_user": get_default_user(db),
                "es_premium": False,
                "max_fuentes": 3,
                "fuentes_actuales": 0,
                "error": f"Error al cargar fuentes: {str(e)}"
            },
        )

@router.post("/add")
async def agregar_fuente(
    request: Request,
    db: Session = Depends(get_db)
):
    """Agrega una nueva fuente a la base de datos"""
    try:
        current_user = get_default_user(db)
        if not current_user:
            # Intentar crear un usuario por defecto (admin) si no existe
            try:
                create_default_user()
                current_user = get_default_user(db)
            except Exception:
                current_user = None

        if not current_user:
            return RedirectResponse(
                url="/sources/?err=Usuario+no+encontrado",
                status_code=303,
            )

        form = await request.form()
        url_listado = (form.get("url_listado") or "").strip()
        nombre = (form.get("nombre") or "").strip() or None

        if not url_listado:
            return RedirectResponse(
                url="/sources/?err=URL+requerida",
                status_code=303,
            )

        # Verificar si la URL ya existe
        exists = db.query(models.Fuente).filter_by(url_listado=url_listado).first()
        if exists:
            return RedirectResponse(
                url="/sources/?err=La+fuente+ya+existe+en+el+sistema",
                status_code=303,
            )

        # Crear la fuente usando el servicio (aplica límites por plan)
        try:
            fuente = svc_add_fuente(db, url_listado=url_listado, nombre=nombre, usuario_id=current_user.id)
        except ValueError as ve:
            return RedirectResponse(url=f"/sources/?err={urlencode({'err': str(ve)})}", status_code=303)
        except Exception as e:
            logger.exception(f"Error creando fuente: {e}")
            return RedirectResponse(url="/sources/?err=Error+interno+al+crear+fuente", status_code=303)

        logger.info(f"✅ [FUENTE] Usuario {current_user.email} agregó fuente id={fuente.id}")

        return RedirectResponse(url="/sources/?msg=Fuente+agregada+correctamente", status_code=303)
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error en agregar_fuente: {e}")
        return RedirectResponse(
            url="/sources/?err=Error+interno+del+servidor",
            status_code=303,
        )

@router.post("/{fuente_id}/enable")
async def habilitar_fuente(
    fuente_id: int, 
    request: Request,
    db: Session = Depends(get_db)
):
    """Habilita una fuente para scraping"""
    try:
        fuente = db.query(models.Fuente).filter(models.Fuente.id == fuente_id).first()
        
        if not fuente:
            return RedirectResponse(
                url="/sources/?err=Fuente+no+encontrada",
                status_code=303,
            )

        fuente.habilitada = True
        fuente.updated_at = datetime.now()
        db.commit()
        
        logger.info(f"✅ [FUENTE] Fuente habilitada id={fuente_id}")
        return RedirectResponse("/sources/?msg=Fuente+habilitada", status_code=303)
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error en habilitar_fuente: {e}")
        return RedirectResponse("/sources/?err=Error+interno", status_code=303)

@router.post("/{fuente_id}/disable")
async def deshabilitar_fuente(
    fuente_id: int, 
    request: Request,
    db: Session = Depends(get_db)
):
    """Deshabilita una fuente"""
    try:
        fuente = db.query(models.Fuente).filter(models.Fuente.id == fuente_id).first()
        
        if not fuente:
            return RedirectResponse(
                url="/sources/?err=Fuente+no+encontrada",
                status_code=303,
            )

        fuente.habilitada = False
        fuente.updated_at = datetime.now()
        db.commit()
        
        logger.info(f"✅ [FUENTE] Fuente deshabilitada id={fuente_id}")
        return RedirectResponse("/sources/?msg=Fuente+deshabilitada", status_code=303)
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error en deshabilitar_fuente: {e}")
        return RedirectResponse("/sources/?err=Error+interno", status_code=303)

@router.post("/{fuente_id}/delete")
async def eliminar_fuente(
    fuente_id: int, 
    request: Request,
    db: Session = Depends(get_db)
):
    """Elimina una fuente"""
    try:
        fuente = db.query(models.Fuente).filter(models.Fuente.id == fuente_id).first()
        
        if not fuente:
            return RedirectResponse(
                url="/sources/?err=Fuente+no+encontrada",
                status_code=303,
            )
        
        logger.info(f"🗑️ [FUENTE] Eliminando fuente: {fuente.nombre} (ID: {fuente.id})")
        
        db.delete(fuente)
        db.commit()
        
        logger.info(f"✅ [FUENTE] Fuente eliminada id={fuente_id}")
        return RedirectResponse("/sources/?msg=Fuente+eliminada", status_code=303)
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error en eliminar_fuente: {e}")
        return RedirectResponse("/sources/?err=Error+al+eliminar+fuente", status_code=303)

# =========================
# RUTAS DE DIAGNÓSTICO
# =========================

@router.get("/debug-fuentes")
def debug_fuentes(db: Session = Depends(get_db)):
    """Diagnóstico de fuentes"""
    fuentes = db.query(models.Fuente).all()
    usuarios = db.query(models.Usuario).all()
    
    resultado = {
        "total_usuarios": len(usuarios),
        "usuarios": [{"id": u.id, "email": u.email, "plan": u.plan} for u in usuarios],
        "total_fuentes": len(fuentes),
        "fuentes": [
            {
                "id": f.id, 
                "nombre": f.nombre, 
                "url": f.url_listado, 
                "usuario_id": f.usuario_id,
                "habilitada": f.habilitada,
                "creada": f.created_at.isoformat() if f.created_at else None
            } for f in fuentes
        ]
    }
    
    logger.info("🔍 [DEBUG_FUENTES]")
    logger.info(f"   Usuarios: {len(usuarios)}")
    logger.info(f"   Fuentes: {len(fuentes)}")
    
    return resultado

@router.get("/test-db")
def test_database(db: Session = Depends(get_db)):
    """Prueba de conexión a base de datos"""
    try:
        usuarios_count = db.query(models.Usuario).count()
        fuentes_count = db.query(models.Fuente).count()
        noticias_count = db.query(models.Noticia).count()
        
        return {
            "status": "success",
            "tablas": {
                "usuarios": usuarios_count,
                "fuentes": fuentes_count,
                "noticias": noticias_count
            },
            "database": "news.db (SQLite)"
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }

@router.get("/debug-scraping")
async def debug_scraping(db: Session = Depends(get_db)):
    """Diagnóstico del sistema de scraping"""
    try:
        current_user = get_default_user(db)
        
        fuentes_totales = db.query(models.Fuente).count()
        fuentes_habilitadas = db.query(models.Fuente).filter(
            models.Fuente.habilitada == True
        ).count()
        
        total_noticias = db.query(models.Noticia).count()
        
        # Probar scraping de una fuente
        fuente_test = db.query(models.Fuente).filter(
            models.Fuente.habilitada == True
        ).first()
        
        test_result = "No hay fuentes para probar"
        if fuente_test:
            test_result = await ejecutar_scraping_fuente(fuente_test.id, db)
        
        return {
            "status": "diagnóstico_scraping",
            "usuario": {
                "id": current_user.id,
                "email": current_user.email
            },
            "fuentes": {
                "totales": fuentes_totales,
                "habilitadas": fuentes_habilitadas,
                "test_fuente": {
                    "id": fuente_test.id if fuente_test else None,
                    "nombre": fuente_test.nombre if fuente_test else None
                }
            },
            "noticias": {
                "totales": total_noticias
            },
            "test_scraping": test_result
        }
        
    except Exception as e:
        return {"error": f"Diagnóstico falló: {str(e)}"}


@router.post("/scrape-all-json")
async def scrapear_todas_fuentes_json(
    request: Request,
    db: Session = Depends(get_db),
):
    """JSON endpoint para scrapear todas las fuentes habilitadas y devolver resultado."""
    try:
        fuentes = db.query(models.Fuente).filter(models.Fuente.habilitada == True).all()
        if not fuentes:
            return JSONResponse({"ok": False, "msg": "No hay fuentes habilitadas para scrapear"}, status_code=200)

        resultados = []
        exitosos = 0
        total_saved = 0
        for fuente in fuentes:
            try:
                saved_articles = await ejecutar_scraping_fuente(fuente.id, db)
                saved_count = len(saved_articles) if isinstance(saved_articles, (list, tuple)) else 0
                resultados.append({
                    "fuente": fuente.nombre or fuente.url_listado,
                    "saved": int(saved_count),
                    "articles": saved_articles if isinstance(saved_articles, list) else []
                })
                if saved_count > 0:
                    exitosos += 1
                    total_saved += int(saved_count)
            except Exception as e:
                resultados.append({"fuente": fuente.nombre or fuente.url_listado, "saved": 0, "error": str(e)})
        msg = f"Scraping completado: {exitosos}/{len(fuentes)} fuentes procesadas, {total_saved} noticias guardadas"
        return JSONResponse({"ok": True, "msg": msg, "total_saved": total_saved, "results": resultados}, status_code=200)
    except Exception as e:
        logger.error(f"💥 Error iniciando scraping JSON: {e}")
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)


@router.post("/{fuente_id}/scrape-json")
async def scrapear_fuente_individual_json(
    fuente_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """JSON endpoint para scrapear una fuente individual y devolver resultado."""
    try:
        fuente = db.query(models.Fuente).filter(models.Fuente.id == fuente_id).first()
        if not fuente:
            return JSONResponse({"ok": False, "msg": "Fuente no encontrada"}, status_code=404)

        if not fuente.habilitada:
            return JSONResponse({"ok": False, "msg": "Fuente deshabilitada"}, status_code=400)

        saved_articles = await ejecutar_scraping_fuente(fuente_id, db)
        saved_count = len(saved_articles) if isinstance(saved_articles, (list, tuple)) else 0
        if saved_count > 0:
            return JSONResponse({
                "ok": True,
                "msg": f"Scraping exitoso para {fuente.nombre or fuente.url_listado}",
                "saved": int(saved_count),
                "articles": saved_articles
            }, status_code=200)
        else:
            return JSONResponse({
                "ok": False,
                "msg": f"No se pudieron procesar artículos para {fuente.nombre or fuente.url_listado}",
                "saved": 0,
                "articles": []
            }, status_code=200)
    except Exception as e:
        logger.error(f"💥 Error en scrape-json fuente {fuente_id}: {e}")
        return JSONResponse({"ok": False, "msg": str(e)}, status_code=500)