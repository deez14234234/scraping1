# app/scripts/force_update_db.py
from app.database import engine, Base, SessionLocal
from app.models import Usuario, Fuente, Noticia, CambioNoticia, SocialMediaPost, PlanBeneficio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def force_update_database():
    """Fuerza la actualización de la base de datos eliminando y recreando las tablas."""
    print("🔄 FORZANDO ACTUALIZACIÓN DE BASE DE DATOS...")
    
    # IMPORTANTE: Esto eliminará todos los datos existentes
    confirm = input("⚠️  ¿Estás seguro? Esto eliminará todos los datos. (s/n): ")
    if confirm.lower() != 's':
        print("❌ Actualización cancelada")
        return
    
    try:
        # Eliminar todas las tablas
        Base.metadata.drop_all(bind=engine)
        print("✅ Tablas eliminadas")
        
        # Crear todas las tablas con la nueva estructura
        Base.metadata.create_all(bind=engine)
        print("✅ Tablas recreadas con nueva estructura")
        
        # Crear usuario admin
        from app.auth import get_password_hash
        db = SessionLocal()
        try:
            admin = Usuario(
                email="admin@nexnews.com",
                nombre="Administrador",
                hashed_password=get_password_hash("admin123"),
                plan="premium",
                activo=True,
                max_fuentes=None,  # Ilimitado para premium
                max_noticias_mes=None,
                max_posts_social_mes=None
            )
            db.add(admin)
            db.commit()
            print("✅ Usuario admin premium creado")
        except Exception as e:
            db.rollback()
            logger.error(f"Error creando usuario admin: {e}")
        finally:
            db.close()
            
        print("🎉 Base de datos actualizada exitosamente")
        
    except Exception as e:
        logger.error(f"❌ Error actualizando base de datos: {e}")

if __name__ == "__main__":
    force_update_database()