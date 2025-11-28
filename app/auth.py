# app/auth.py
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Usuario
from app.schemas import TokenData, UsuarioLogin 

# Configuración
SECRET_KEY = "tu_clave_secreta_super_segura_cambiar_en_produccion"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Contexto para hashing de passwords
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
security = HTTPBearer()

router = APIRouter()

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def authenticate_user(db: Session, email: str, password: str):
    usuario = db.query(Usuario).filter(Usuario.email == email).first()
    if not usuario:
        return False
    if not verify_password(password, usuario.hashed_password):
        return False
    return usuario

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=email)
    except JWTError:
        raise credentials_exception
    
    usuario = db.query(Usuario).filter(Usuario.email == token_data.email).first()
    if usuario is None:
        raise credentials_exception
    return usuario

async def get_current_active_user(current_user: Usuario = Depends(get_current_user)):
    if not current_user.activo:
        raise HTTPException(status_code=400, detail="Usuario inactivo")
    return current_user

def es_usuario_premium(current_user: Usuario = Depends(get_current_active_user)):
    if current_user.plan != "premium":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Se requiere plan premium para acceder a esta funcionalidad"
        )
    return current_user

@router.post("/login")
async def login_for_access_token(
    form_data: UsuarioLogin,
    db: Session = Depends(get_db)
):
    user = authenticate_user(db, form_data.email, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos",
        )
    
    # Actualizar último login
    user.ultimo_login = datetime.utcnow()
    db.commit()
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "usuario": user
    }

@router.get("/me")
async def read_users_me(current_user: Usuario = Depends(get_current_active_user)):
    return current_user

# Nuevas funciones para autenticación web
async def web_authenticate_user(request: Request, email: str, password: str, db: Session):
    """Autenticación para la interfaz web con sesiones"""
    user = authenticate_user(db, email, password)
    if user:
        # Establecer sesión
        request.session["user_id"] = user.id
        request.session["user_email"] = user.email
        request.session["user_plan"] = user.plan
        return user
    return None

async def web_logout(request: Request):
    """Cerrar sesión web"""
    request.session.clear()
    return RedirectResponse("/web/login", status_code=302)