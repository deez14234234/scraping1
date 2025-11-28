# app/routes/categories.py
from fastapi import APIRouter, Request, Depends, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.database import get_db
from app.models import Noticia

router = APIRouter(prefix="/web/categories", tags=["Categorías Web"])


@router.get("/", response_class=HTMLResponse)
async def listar_categorias(request: Request, db: Session = Depends(get_db)):
    """
    Lista todas las categorías disponibles con conteo de noticias.
    """
    categorias = db.query(
        Noticia.categoria,
    ).filter(Noticia.categoria.isnot(None)).distinct().all()
    
    categoria_list = []
    for cat in categorias:
        if cat[0]:
            count = db.query(Noticia).filter(Noticia.categoria == cat[0]).count()
            categoria_list.append({"nombre": cat[0], "count": count})
    
    return templates.TemplateResponse(
        "categories.html",
        {"request": request, "categorias": categoria_list}
    )
