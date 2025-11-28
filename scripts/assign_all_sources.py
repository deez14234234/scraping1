# app/scripts/assign_all_sources.py
from app.database import SessionLocal
from app.models import Usuario, Fuente

def assign_all_sources():
    """Asigna todas las fuentes existentes al usuario admin."""
    print("🔄 ASIGNANDO TODAS LAS FUENTES AL ADMIN...")
    
    db = SessionLocal()
    try:
        # Obtener usuario admin
        admin = db.query(Usuario).filter(Usuario.email == "admin@nexnews.com").first()
        if not admin:
            print("❌ No se encontró el usuario admin")
            return
        
        # Contar y asignar fuentes sin usuario
        fuentes_sin_usuario = db.query(Fuente).filter(Fuente.usuario_id.is_(None)).count()
        print(f"📦 Encontradas {fuentes_sin_usuario} fuentes sin usuario")
        
        if fuentes_sin_usuario > 0:
            db.query(Fuente).filter(Fuente.usuario_id.is_(None)).update(
                {"usuario_id": admin.id},
                synchronize_session=False
            )
            db.commit()
            print(f"✅ {fuentes_sin_usuario} fuentes asignadas al admin")
        
        # Verificar resultado
        total_fuentes_admin = db.query(Fuente).filter(Fuente.usuario_id == admin.id).count()
        print(f"📊 Admin ahora tiene {total_fuentes_admin} fuentes")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error asignando fuentes: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    assign_all_sources()