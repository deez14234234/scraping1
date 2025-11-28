# app/auth_web.py
from fastapi import Request, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Usuario

async def get_current_user_from_session(request: Request, db: Session = Depends(get_db)):
    """Obtiene el usuario actual desde la sesión (para rutas web)"""
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse("/web/login", status_code=303)
    
    user = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not user or not user.activo:
        request.session.clear()
        return RedirectResponse("/web/login", status_code=303)
    
    return user