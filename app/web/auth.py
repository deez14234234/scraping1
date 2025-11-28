# app/web/auth.py
from fastapi import Request, HTTPException, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Usuario

async def get_current_user_web(request: Request, db: Session = Depends(get_db)):
    """Obtiene el usuario actual para la interfaz web (sesiones)"""
    # Verificar si hay usuario en sesión
    user_id = request.session.get("user_id")
    if not user_id:
        # Redirigir al login si no está autenticado
        return RedirectResponse("/web/login")
    
    # Obtener usuario de la base de datos
    user = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not user:
        # Limpiar sesión inválida
        request.session.clear()
        return RedirectResponse("/web/login")
    
    return user

async def get_current_active_user_web(current_user: Usuario = Depends(get_current_user_web)):
    """Verifica que el usuario esté activo"""
    if not current_user.activo:
        raise HTTPException(status_code=400, detail="Usuario inactivo")
    return current_user