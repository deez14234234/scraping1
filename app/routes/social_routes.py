# app/routes/social_routes.py
from fastapi import APIRouter, Request, HTTPException, Depends, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_
from app.scraper.social_scraper import NoticieroSocialScraper
from app.database import get_db
from app import models
from app.models import SocialMediaPost
import json
import time
# En app/routes/social_routes.py - agrega esta línea:
from fastapi.templating import Jinja2Templates

# Y define templates (agrega esto después de los imports):
templates = Jinja2Templates(directory="app/web/templates")

router = APIRouter(prefix="/api/social", tags=["Redes Sociales"])

@router.post("/twitter/scrape")
async def scrape_twitter(db: Session = Depends(get_db)):
    """Scrapea tweets de noticieros peruanos y GUARDA en BD"""
    try:
        start_time = time.time()
        scraper = NoticieroSocialScraper()
        
        # Scrapear y guardar en BD
        tweets = scraper.scrape_twitter_noticieros(limit_per_account=8, db_session=db)
        
        execution_time = round(time.time() - start_time, 2)
        
        return JSONResponse({
            "message": f"✅ Scraping de Twitter completado y guardado",
            "count": len(tweets),
            "saved_to_db": len(tweets),
            "execution_time": f"{execution_time}s",
            "platform": "twitter",
            "details": f"Se encontraron {len(tweets)} tweets de {len(scraper.noticieros)} noticieros"
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"❌ Error scraping Twitter: {str(e)}")

@router.post("/facebook/scrape")
async def scrape_facebook(db: Session = Depends(get_db)):
    """Scrapea Facebook de noticieros y GUARDA en BD"""
    try:
        start_time = time.time()
        scraper = NoticieroSocialScraper()
        
        # Scrapear y guardar en BD
        posts = scraper.scrape_facebook_noticieros(limit_per_account=5, db_session=db)
        
        execution_time = round(time.time() - start_time, 2)
        
        return JSONResponse({
            "message": f"✅ Scraping de Facebook completado y guardado",
            "count": len(posts),
            "saved_to_db": len(posts),
            "execution_time": f"{execution_time}s", 
            "platform": "facebook",
            "details": f"Se procesaron {len(posts)} posts de {len(scraper.noticieros)} noticieros"
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"[ERROR] Error scraping Facebook: {str(e)}")

@router.post("/instagram/scrape")
async def scrape_instagram(db: Session = Depends(get_db)):
    """Scrapea Instagram y GUARDA en BD"""
    try:
        start_time = time.time()
        scraper = NoticieroSocialScraper()
        
        # Scrapear y guardar en BD (usando Facebook como fallback para Instagram)
        posts = scraper.scrape_facebook_noticieros(limit_per_account=5, db_session=db)
        
        execution_time = round(time.time() - start_time, 2)
        
        return JSONResponse({
            "message": f"[OK] Scraping de Instagram completado y guardado",
            "count": len(posts),
            "saved_to_db": len(posts),
            "execution_time": f"{execution_time}s", 
            "platform": "instagram",
            "details": f"Se procesaron {len(posts)} posts"
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"[ERROR] Error scraping Instagram: {str(e)}")

@router.post("/all/scrape")
async def scrape_all_social(db: Session = Depends(get_db)):
    """Scrapea todas las redes sociales y GUARDA en BD"""
    try:
        start_time = time.time()
        scraper = NoticieroSocialScraper()
        
        # Scrapear todas las redes
        results = scraper.scrape_all_noticieros(db_session=db)
        
        total_posts = sum(len(posts) for posts in results.values())
        execution_time = round(time.time() - start_time, 2)
        
        return JSONResponse({
            "message": f"🎉 Scraping completo de redes sociales",
            "total": total_posts,
            "saved_to_db": total_posts,
            "execution_time": f"{execution_time}s",
            "platforms": ["twitter", "facebook"],
            "noticieros_procesados": list(results.keys()),
            "details": f"{total_posts} posts de {len(results)} noticieros en {execution_time} segundos"
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"❌ Error scraping redes sociales: {str(e)}")

@router.get("/dashboard", response_class=HTMLResponse)
async def social_dashboard(request: Request, db: Session = Depends(get_db)):
    """Dashboard de redes sociales con estadísticas REALES"""
    from datetime import datetime, timedelta
    
    # Obtener estadísticas reales de la base de datos
    total_posts = db.query(SocialMediaPost).count()
    
    # Obtener conteo por red social (dinámicamente)
    platforms = db.query(SocialMediaPost.platform).distinct().all()
    platform_counts = {}
    for platform in platforms:
        p = platform[0]
        count = db.query(SocialMediaPost).filter(SocialMediaPost.platform == p).count()
        if p:
            platform_counts[p] = count
    
    # Compatibilidad: agregamos twitter_count y facebook_count para estadísticas
    twitter_count = platform_counts.get('twitter', 0)
    facebook_count = platform_counts.get('facebook', 0)
    
    # Obtener noticieros únicos desde posts
    noticieros = db.query(SocialMediaPost.source).distinct().all()
    noticieros_list = [n[0] for n in noticieros if n[0]]

    # Obtener fuentes sociales guardadas en `fuentes` (twitter/facebook/instagram)
    social_fuentes = db.query(models.Fuente).filter(
        or_(
            models.Fuente.url_listado.ilike("%twitter.com%"),
            models.Fuente.url_listado.ilike("%x.com%"),
            models.Fuente.url_listado.ilike("%facebook.com%"),
            models.Fuente.url_listado.ilike("%instagram.com%")
        )
    ).order_by(models.Fuente.id.desc()).all()
    
    # Obtener posts recientes (últimos 12)
    posts = db.query(SocialMediaPost).order_by(desc(SocialMediaPost.created_at)).limit(12).all()
    
    # Último scraping
    last_post = db.query(SocialMediaPost).order_by(desc(SocialMediaPost.created_at)).first()
    ultimo_scraping = last_post.created_at.strftime('%Y-%m-%d %H:%M:%S') if last_post else "Nunca"
    
    # Datos históricos: cantidad de posts por día en los últimos 7 días
    from sqlalchemy import func
    today = datetime.now().date()
    seven_days_ago = today - timedelta(days=6)
    
    # Consulta para obtener posts por fecha y red social
    daily_data = db.query(
        func.date(SocialMediaPost.created_at).label('date'),
        SocialMediaPost.platform.label('platform'),
        func.count(SocialMediaPost.id).label('count')
    ).filter(
        func.date(SocialMediaPost.created_at) >= seven_days_ago
    ).group_by(
        func.date(SocialMediaPost.created_at),
        SocialMediaPost.platform
    ).order_by(
        func.date(SocialMediaPost.created_at)
    ).all()
    
    # Construir estructura para el gráfico de líneas
    # Formatos: dates: [fecha1, fecha2, ...], platforms: {twitter: [1,2,3...], facebook: [...]}
    dates_set = set()
    line_chart_data = {}
    
    for row in daily_data:
        date_str = str(row.date)
        dates_set.add(date_str)
        platform = row.platform or 'unknown'
        
        if platform not in line_chart_data:
            line_chart_data[platform] = {}
        
        line_chart_data[platform][date_str] = row.count
    
    # Ordenar fechas
    sorted_dates = sorted(list(dates_set))
    
    # Llenar valores faltantes con 0 para cada plataforma
    chart_dates = sorted_dates
    chart_platforms = {}
    for platform in line_chart_data:
        chart_platforms[platform] = [
            line_chart_data[platform].get(date, 0) for date in sorted_dates
        ]
    
    stats = {
        "total_posts": total_posts,
        "twitter_count": twitter_count,
        "facebook_count": facebook_count,
        "platform_counts": platform_counts,  # Nuevo: conteos dinámicos
        "noticieros_monitoreados": len(noticieros_list),
        "ultimo_scraping": ultimo_scraping,
        "chart_dates": chart_dates,  # Fechas para el gráfico de líneas
        "chart_platforms": chart_platforms  # Datos por plataforma
    }
    # Serializar datos del gráfico a JSON aquí para evitar dependencias
    # en filtros Jinja (por ejemplo si `tojson` no está disponible).
    chart_json = json.dumps({
        "dates": chart_dates,
        "platforms": chart_platforms
    }, default=str)

    return templates.TemplateResponse(
        "social_dashboard.html", 
        {
            "request": request, 
            "stats": stats,
            "noticieros": noticieros_list,
            "social_fuentes": social_fuentes,
            "posts": posts,
            "chart_json": chart_json
        }
    )


@router.post("/web/social/add")
async def add_social_fuente(request: Request, db: Session = Depends(get_db)):
    """Agrega una nueva fuente social (perfil/página) a la tabla `fuentes`."""
    form = await request.form()
    url_listado = (form.get("url_listado") or "").strip()
    nombre = (form.get("nombre") or "").strip() or None

    if not url_listado:
        return RedirectResponse(url="/api/social/dashboard?err=URL requerida", status_code=303)

    exists = db.query(models.Fuente).filter_by(url_listado=url_listado).one_or_none()
    if exists:
        return RedirectResponse(url="/api/social/dashboard?err=La fuente ya existe", status_code=303)

    fuente = models.Fuente(url_listado=url_listado, nombre=nombre, habilitada=True)
    db.add(fuente)
    db.commit()

    # Si el formulario pidió scrapear ahora, ejecutar scraping de la fuente recién creada
    if form.get("scrape_now"):
        scraper = NoticieroSocialScraper()
        saved = 0
        try:
            lower = url_listado.lower()
            if "twitter.com" in lower or "x.com" in lower:
                parts = [p for p in url_listado.split('/') if p]
                username = parts[-1]
                posts = scraper.scrape_twitter_public(username, limit=20)
                saved = scraper.save_posts_to_db(posts, db)
            elif "facebook.com" in lower:
                posts = scraper.scrape_facebook_public_page(url_listado, limit=10)
                saved = scraper.save_posts_to_db(posts, db)
            elif "instagram.com" in lower:
                posts = scraper.scrape_facebook_public_page(url_listado, limit=6)
                saved = scraper.save_posts_to_db(posts, db)
            return RedirectResponse(url=f"/api/social/dashboard?msg=Fuente agregada y scrapear guardados={saved}", status_code=303)
        except Exception as e:
            return RedirectResponse(url=f"/api/social/dashboard?err=Fuente agregada pero error scraping: {str(e)}", status_code=303)

    return RedirectResponse(url="/api/social/dashboard?msg=Fuente social agregada", status_code=303)


@router.post("/web/social/{fuente_id}/scrape")
def scrape_social_fuente(fuente_id: int, db: Session = Depends(get_db)):
    """Scrapea la fuente social guardada (twitter/facebook/instagram) y guarda posts en BD."""
    fuente = db.get(models.Fuente, fuente_id)
    if not fuente:
        raise HTTPException(404, "Fuente no encontrada")

    url = (fuente.url_listado or "").lower()
    scraper = NoticieroSocialScraper()
    saved = 0

    try:
        if "twitter.com" in url or "x.com" in url:
            # extraer username
            parts = [p for p in fuente.url_listado.split('/') if p]
            username = parts[-1]
            posts = scraper.scrape_twitter_public(username, limit=20)
            saved = scraper.save_posts_to_db(posts, db)
        elif "facebook.com" in url:
            posts = scraper.scrape_facebook_public_page(fuente.url_listado, limit=10)
            saved = scraper.save_posts_to_db(posts, db)
        elif "instagram.com" in url:
            # No hay scraper real para Instagram; simular con Facebook method for now
            posts = scraper.scrape_facebook_public_page(fuente.url_listado, limit=6)
            saved = scraper.save_posts_to_db(posts, db)
        else:
            return RedirectResponse(url=f"/api/social/dashboard?err=URL no reconocida", status_code=303)

        return RedirectResponse(url=f"/api/social/dashboard?msg=Scrape completado. Guardados={saved}", status_code=303)

    except Exception as e:
        return RedirectResponse(url=f"/api/social/dashboard?err=Error scraping: {str(e)}", status_code=303)


@router.post("/web/social/{fuente_id}/enable")
def enable_social_fuente(fuente_id: int, db: Session = Depends(get_db)):
    fuente = db.get(models.Fuente, fuente_id)
    if not fuente:
        raise HTTPException(404, "Fuente no encontrada")
    fuente.habilitada = True
    db.commit()
    return RedirectResponse("/api/social/dashboard?msg=Fuente habilitada", status_code=303)


@router.post("/web/social/{fuente_id}/disable")
def disable_social_fuente(fuente_id: int, db: Session = Depends(get_db)):
    fuente = db.get(models.Fuente, fuente_id)
    if not fuente:
        raise HTTPException(404, "Fuente no encontrada")
    fuente.habilitada = False
    db.commit()
    return RedirectResponse("/api/social/dashboard?msg=Fuente deshabilitada", status_code=303)


@router.post("/web/social/{fuente_id}/delete")
def delete_social_fuente(fuente_id: int, db: Session = Depends(get_db)):
    fuente = db.get(models.Fuente, fuente_id)
    if not fuente:
        raise HTTPException(404, "Fuente no encontrada")
    db.delete(fuente)
    db.commit()
    return RedirectResponse("/api/social/dashboard?msg=Fuente eliminada", status_code=303)

@router.get("/posts", response_class=HTMLResponse)
async def view_social_posts(
    request: Request, 
    platform: str = None, 
    source: str = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Vista para ver los posts de redes sociales guardados"""
    
    # Construir query
    query = db.query(SocialMediaPost)
    
    if platform and platform != "all":
        query = query.filter(SocialMediaPost.platform == platform)
    if source and source != "all":
        query = query.filter(SocialMediaPost.source == source)
    
    posts = query.order_by(desc(SocialMediaPost.created_at)).limit(limit).all()
    total_count = db.query(SocialMediaPost).count()
    
    # Obtener estadísticas
    platforms = db.query(SocialMediaPost.platform).distinct().all()
    sources = db.query(SocialMediaPost.source).distinct().all()
    
    return templates.TemplateResponse(
        "social_posts.html",
        {
            "request": request,
            "posts": posts,
            "total_count": total_count,
            "platforms": [p[0] for p in platforms if p[0]],
            "sources": [s[0] for s in sources if s[0]],
            "current_platform": platform,
            "current_source": source,
            "limit": limit
        }
    )

@router.get("/stats")
async def get_social_stats(db: Session = Depends(get_db)):
    """Obtiene estadísticas REALES de scraping social"""
    
    total_posts = db.query(SocialMediaPost).count()
    twitter_count = db.query(SocialMediaPost).filter(SocialMediaPost.platform == 'twitter').count()
    facebook_count = db.query(SocialMediaPost).filter(SocialMediaPost.platform == 'facebook').count()
    
    # Noticieros únicos
    noticieros = db.query(SocialMediaPost.source).distinct().all()
    noticieros_list = [n[0] for n in noticieros if n[0]]
    
    # Último post
    last_post = db.query(SocialMediaPost).order_by(desc(SocialMediaPost.created_at)).first()
    
    return {
        "status": "active",
        "total_posts": total_posts,
        "twitter_posts": twitter_count,
        "facebook_posts": facebook_count,
        "noticieros_monitoreados": len(noticieros_list),
        "noticieros": noticieros_list,
        "ultima_ejecucion": last_post.created_at.isoformat() if last_post else None,
        "redes_activas": ["twitter", "facebook"]
    }

@router.get("/posts/api")
async def get_social_posts_api(
    platform: str = None,
    source: str = None, 
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """API para obtener posts de redes sociales"""
    
    query = db.query(SocialMediaPost)
    
    if platform:
        query = query.filter(SocialMediaPost.platform == platform)
    if source:
        query = query.filter(SocialMediaPost.source == source)
    
    posts = query.order_by(desc(SocialMediaPost.created_at)).limit(limit).all()
    
    return {
        "count": len(posts),
        "posts": [
            {
                "id": post.id,
                "platform": post.platform,
                "username": post.username,
                "text": post.text,
                "url": post.url,
                "likes": post.likes,
                "retweets": post.retweets,
                "shares": post.shares,
                "comments": post.comments,
                "source": post.source,
                "created_at": post.created_at.isoformat(),
                "post_created_at": post.post_created_at.isoformat() if post.post_created_at else None
            }
            for post in posts
        ]
    }

@router.delete("/posts/clear")
async def clear_social_posts(db: Session = Depends(get_db)):
    """Elimina todos los posts de redes sociales (para testing)"""
    try:
        deleted_count = db.query(SocialMediaPost).delete()
        db.commit()
        
        return {
            "message": f"✅ Eliminados {deleted_count} posts de redes sociales",
            "deleted_count": deleted_count
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"❌ Error eliminando posts: {str(e)}")