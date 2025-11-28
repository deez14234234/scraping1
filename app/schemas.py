# app/schemas.py
from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, List

# ... tus otros esquemas existentes ...

class CambioNoticiaOut(BaseModel):
    id: int
    campo: str
    valor_anterior: Optional[str]
    valor_nuevo: Optional[str]
    detected_at: datetime

    class Config:
        from_attributes = True

class NoticiaOut(BaseModel):
    id: int
    url: str
    fuente: str
    titulo: str
    contenido: str
    fecha_publicacion: Optional[datetime]
    imagen_path: Optional[str]
    categoria: Optional[str]
    created_at: datetime
    updated_at: datetime
    cambios: List[CambioNoticiaOut] = []

    class Config:
        from_attributes = True

class UsuarioBase(BaseModel):
    email: EmailStr
    nombre: str

class UsuarioCreate(UsuarioBase):
    password: str

class UsuarioLogin(BaseModel):
    email: EmailStr
    password: str

class UsuarioResponse(UsuarioBase):
    id: int
    plan: str
    activo: bool
    fecha_registro: datetime
    ultimo_login: Optional[datetime]
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    usuario: UsuarioResponse

class TokenData(BaseModel):
    email: Optional[str] = None