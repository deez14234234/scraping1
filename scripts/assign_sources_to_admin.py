# app/scripts/assign_sources_to_admin.py
from app.database import SessionLocal
from app.models import Usuario, Fuente

def assign_sources_to_admin():
    """Asigna todas las fuentes existentes al usuario admin."""
    print("🔄 ASIGNANDO FUENTES EXISTENTES AL USUARIO ADMIN...")
    
    db = SessionLocal()
    try:
        # Obtener usuario admin
        admin = db.query(Usuario).filter(Usuario.email == "admin@nexnews.com").first()
        if not admin:
            print("❌ No se encontró el usuario admin")
            return
        
        # Contar fuentes sin usuario
        fuentes_sin_usuario = db.query(Fuente).filter(Fuente.usuario_id.is_(None)).count()
        print(f"📦 Encontradas {fuentes_sin_usuario} fuentes sin usuario asignado")
        
        if fuentes_sin_usuario > 0:
            # Asignar todas las fuentes al admin
            db.query(Fuente).filter(Fuente.usuario_id.is_(None)).update(
                {"usuario_id": admin.id},
                synchronize_session=False
            )
            db.commit()
            print(f"✅ {fuentes_sin_usuario} fuentes asignadas al usuario admin")
        else:
            print("✅ Todas las fuentes ya tienen usuario asignado")
        
        # Verificar resultado
        fuentes_admin = db.query(Fuente).filter(Fuente.usuario_id == admin.id).count()
        print(f"📊 Usuario admin ahora tiene {fuentes_admin} fuentes")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error asignando fuentes: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    assign_sources_to_admin()