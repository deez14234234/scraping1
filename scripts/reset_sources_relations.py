# app/scripts/reset_sources_relations.py
from app.database import SessionLocal
from app.models import Usuario, Fuente

def reset_sources_relations():
    """Resetea completamente las relaciones usuario-fuente."""
    print("🔄 RESETEANDO RELACIONES USUARIO-FUENTE...")
    
    db = SessionLocal()
    try:
        # Obtener usuario admin
        admin = db.query(Usuario).filter(Usuario.email == "admin@nexnews.com").first()
        if not admin:
            print("❌ No se encontró el usuario admin")
            return
        
        # 1. Contar fuentes totales
        total_fuentes = db.query(Fuente).count()
        print(f"📦 Total de fuentes en sistema: {total_fuentes}")
        
        # 2. Resetear todas las relaciones (asignar todas al admin)
        print("🔄 Asignando TODAS las fuentes al admin...")
        db.query(Fuente).update(
            {"usuario_id": admin.id},
            synchronize_session=False
        )
        
        db.commit()
        print(f"✅ {total_fuentes} fuentes asignadas al admin")
        
        # 3. Verificar
        fuentes_admin = db.query(Fuente).filter(Fuente.usuario_id == admin.id).count()
        print(f"📊 Verificación: Admin tiene {fuentes_admin} fuentes")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error reseteando relaciones: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    reset_sources_relations()