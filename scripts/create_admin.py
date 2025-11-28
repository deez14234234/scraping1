# app/scripts/create_admin.py
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.database import init_db, get_db
from app.models import Usuario
from app.auth import get_password_hash

def crear_usuario_inicial():
    init_db()
    db = next(get_db())
    
    # Verificar si ya existe un usuario
    usuario_existente = db.query(Usuario).filter(Usuario.email == "admin@nexnews.com").first()
    
    if not usuario_existente:
        usuario = Usuario(
            email="admin@nexnews.com",
            nombre="Administrador",
            hashed_password=get_password_hash("admin123"),
            plan="premium",
            activo=True
        )
        db.add(usuario)
        db.commit()
        db.refresh(usuario)
        print("✅ Usuario administrador creado:")
        print(f"   Email: admin@nexnews.com")
        print(f"   Contraseña: admin123")
        print(f"   Plan: premium")
    else:
        print("ℹ️  El usuario administrador ya existe")
    
    db.close()

if __name__ == "__main__":
    crear_usuario_inicial()