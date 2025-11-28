# app/scripts/add_social_user_column.py
from app.database import engine
from sqlalchemy import text

def add_social_user_column():
    """Agrega la columna usuario_id a la tabla social_media_posts."""
    print("🔄 AGREGANDO COLUMNA usuario_id A social_media_posts...")
    
    try:
        with engine.connect() as conn:
            # Verificar si la columna ya existe
            result = conn.execute(text("PRAGMA table_info(social_media_posts)")).fetchall()
            existing_columns = [row[1] for row in result]
            
            if "usuario_id" not in existing_columns:
                print("➕ Agregando columna usuario_id...")
                conn.execute(text("ALTER TABLE social_media_posts ADD COLUMN usuario_id INTEGER"))
                conn.commit()
                print("✅ Columna usuario_id agregada a social_media_posts")
            else:
                print("✅ Columna usuario_id ya existe en social_media_posts")
                
    except Exception as e:
        print(f"❌ Error agregando columna: {e}")

if __name__ == "__main__":
    add_social_user_column()