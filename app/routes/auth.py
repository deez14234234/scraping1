# app/routes/auth.py
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import timedelta

from app.database import get_db
from app.models import Usuario
from app.schemas import UsuarioCreate, UsuarioLogin, Token, UsuarioResponse
from app.auth import (
    authenticate_user, create_access_token, 
    get_password_hash, get_current_active_user,
    web_authenticate_user, web_logout,
    ACCESS_TOKEN_EXPIRE_MINUTES
)

from fastapi.templating import Jinja2Templates
templates = Jinja2Templates(directory="app/web/templates")

router = APIRouter()

# --- API Routes ---

@router.post("/registrar", response_model=Token)
async def registrar_usuario(usuario: UsuarioCreate, db: Session = Depends(get_db)):
    # Verificar si el usuario ya existe
    db_usuario = db.query(Usuario).filter(Usuario.email == usuario.email).first()
    if db_usuario:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El email ya está registrado"
        )
    
    # Crear nuevo usuario
    hashed_password = get_password_hash(usuario.password)
    db_usuario = Usuario(
        email=usuario.email,
        nombre=usuario.nombre,
        hashed_password=hashed_password,
        plan="gratis",  # Por defecto plan gratis
        activo=True
    )
    
    db.add(db_usuario)
    db.commit()
    db.refresh(db_usuario)
    
    # Crear token de acceso
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": usuario.email}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "usuario": UsuarioResponse.from_orm(db_usuario)
    }

@router.post("/login", response_model=Token)
async def login(usuario: UsuarioLogin, db: Session = Depends(get_db)):
    user = authenticate_user(db, usuario.email, usuario.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Actualizar último login
    from datetime import datetime
    user.ultimo_login = datetime.now()
    db.commit()
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "usuario": UsuarioResponse.from_orm(user)
    }

@router.get("/me", response_model=UsuarioResponse)
async def leer_usuario_actual(current_user: Usuario = Depends(get_current_active_user)):
    return current_user

# --- Web Routes ---

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/login")
async def web_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    user = await web_authenticate_user(request, email, password, db)
    if not user:
        # Redirigir con error
        return RedirectResponse("/web/login?error=Credenciales+incorrectas", status_code=303)
    
    # Redirigir al dashboard o sources
    return RedirectResponse("/web/sources", status_code=303)

@router.get("/registro", response_class=HTMLResponse)
async def registro_page(request: Request):
    return templates.TemplateResponse("registro.html", {"request": request})

@router.post("/registro")
async def web_registro(
    request: Request,
    email: str = Form(...),
    nombre: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # Verificar si el usuario ya existe
    db_usuario = db.query(Usuario).filter(Usuario.email == email).first()
    if db_usuario:
        return RedirectResponse("/web/registro?error=El+email+ya+está+registrado", status_code=303)
    
    # Crear nuevo usuario
    hashed_password = get_password_hash(password)
    db_usuario = Usuario(
        email=email,
        nombre=nombre,
        hashed_password=hashed_password,
        plan="gratis",
        activo=True
    )
    
    db.add(db_usuario)
    db.commit()
    
    # Iniciar sesión automáticamente
    await web_authenticate_user(request, email, password, db)
    
    return RedirectResponse("/web/sources", status_code=303)

@router.get("/logout")
async def logout_web(request: Request):
    return await web_logout(request)