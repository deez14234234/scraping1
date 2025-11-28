# app/scripts/add_missing_columns.py
from app.database import engine, SessionLocal
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_missing_columns():
    """Agrega solo las columnas faltantes sin eliminar datos."""
    print("🔄 AGREGANDO COLUMNAS FALTANTES...")
    
    db = SessionLocal()
    try:
        # Verificar y agregar columnas faltantes en la tabla usuarios
        columns_to_add = [
            ("max_fuentes", "INTEGER"),
            ("max_noticias_mes", "INTEGER"), 
            ("max_posts_social_mes", "INTEGER")
        ]
        
        for column_name, column_type in columns_to_add:
            # Verificar si la columna existe
            result = db.execute(text(f"PRAGMA table_info(usuarios)")).fetchall()
            existing_columns = [row[1] for row in result]
            
            if column_name not in existing_columns:
                print(f"➕ Agregando columna: {column_name}")
                db.execute(text(f"ALTER TABLE usuarios ADD COLUMN {column_name} {column_type}"))
                db.commit()
                print(f"✅ Columna {column_name} agregada")
            else:
                print(f"✅ Columna {column_name} ya existe")
        
        # Actualizar usuarios existentes
        print("🔄 Actualizando límites de usuarios existentes...")
        
        # Usuarios gratis: límites por defecto
        db.execute(text("UPDATE usuarios SET max_fuentes = 3, max_noticias_mes = 100, max_posts_social_mes = 500 WHERE plan = 'gratis'"))
        
        # Usuarios premium: límites ilimitados (NULL)
        db.execute(text("UPDATE usuarios SET max_fuentes = NULL, max_noticias_mes = NULL, max_posts_social_mes = NULL WHERE plan = 'premium'"))
        
        db.commit()
        print("✅ Límites de usuarios actualizados")
        
        print("🎉 Columnas faltantes agregadas exitosamente")
        
    except Exception as e:
        db.rollback()
        logger.error(f"❌ Error agregando columnas: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    add_missing_columns()