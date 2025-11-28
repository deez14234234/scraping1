from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime, timedelta

from app.database import get_db
from app import models
from app.schemas import NoticiaOut
# ✅ Corregir esta importación

router = APIRouter(prefix="/news", tags=["Noticias"])

# =====================================================
# 🌐 RUTAS API (JSON)
# =====================================================

# 🗂️ Obtener categorías únicas (para filtros del frontend)
@router.get("/categorias", response_model=List[str])
def get_categorias(db: Session = Depends(get_db)):
    """
    Retorna todas las categorías únicas registradas en las noticias.
    """
    categorias = db.query(models.Noticia.categoria).distinct().all()
    return [c[0] for c in categorias if c[0]]


# 📰 Listar noticias con filtros
@router.get("/", response_model=List[NoticiaOut])
def list_news(
    q: Optional[str] = Query(None, description="Buscar en título o contenido"),
    fuente: Optional[str] = Query(None, description="Filtrar por fuente o dominio"),
    categoria: Optional[str] = Query(None, description="Filtrar por categoría"),
    limit: int = Query(50, ge=1, le=200, description="Límite máximo de resultados"),
    offset: int = Query(0, ge=0, description="Desplazamiento para paginación"),
    db: Session = Depends(get_db),
):
    """
    Devuelve una lista de noticias con soporte de búsqueda y filtros.
    """
    stmt = select(models.Noticia).order_by(models.Noticia.created_at.desc())

    if fuente:
        stmt = stmt.where(models.Noticia.fuente.ilike(f"%{fuente}%"))
    if categoria:
        stmt = stmt.where(models.Noticia.categoria.ilike(f"%{categoria}%"))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                models.Noticia.titulo.ilike(like),
                models.Noticia.contenido.ilike(like)
            )
        )

    stmt = stmt.limit(limit).offset(offset)
    noticias = db.scalars(stmt).all()
    return noticias


# 📰 Obtener detalle de una noticia (API)
@router.get("/{noticia_id}", response_model=NoticiaOut)
def get_news(noticia_id: int, db: Session = Depends(get_db)):
    """
    Devuelve los detalles de una noticia específica por ID.
    """
    noticia = db.get(models.Noticia, noticia_id)
    if not noticia:
        raise HTTPException(status_code=404, detail="Noticia no encontrada")
    return noticia


# 🧹 Eliminar noticias antiguas (mantenimiento)
@router.delete("/purge")
def purge_old_news(
    days: int = Query(180, description="Eliminar noticias con más de N días"),
    db: Session = Depends(get_db),
):
    """
    Elimina noticias antiguas (por defecto mayores a 180 días).
    """
    cutoff = datetime.utcnow() - timedelta(days=days)
    deleted = (
        db.query(models.Noticia)
        .filter(models.Noticia.created_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"message": f"{deleted} noticias eliminadas con más de {days} días"}


