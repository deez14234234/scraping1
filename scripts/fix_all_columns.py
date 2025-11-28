# app/scripts/fix_all_columns.py
from app.database import engine
from sqlalchemy import text

def fix_all_columns():
    """Soluciona todos los problemas de columnas faltantes."""
    print("🔧 SOLUCIONANDO TODAS LAS COLUMNAS FALTANTES...")
    
    try:
        with engine.connect() as conn:
            # 1. Verificar y agregar columnas en usuarios
            print("📋 Verificando tabla usuarios...")
            result = conn.execute(text("PRAGMA table_info(usuarios)")).fetchall()
            user_columns = [row[1] for row in result]
            
            user_columns_to_add = [
                ("max_fuentes", "INTEGER"),
                ("max_noticias_mes", "INTEGER"),
                ("max_posts_social_mes", "INTEGER")
            ]
            
            for column_name, column_type in user_columns_to_add:
                if column_name not in user_columns:
                    print(f"➕ Agregando {column_name} a usuarios...")
                    conn.execute(text(f"ALTER TABLE usuarios ADD COLUMN {column_name} {column_type}"))
            
            # 2. Verificar y agregar usuario_id en fuentes
            print("📋 Verificando tabla fuentes...")
            result = conn.execute(text("PRAGMA table_info(fuentes)")).fetchall()
            fuente_columns = [row[1] for row in result]
            
            if "usuario_id" not in fuente_columns:
                print("➕ Agregando usuario_id a fuentes...")
                conn.execute(text("ALTER TABLE fuentes ADD COLUMN usuario_id INTEGER"))
            
            # 3. Verificar y agregar usuario_id en social_media_posts
            print("📋 Verificando tabla social_media_posts...")
            result = conn.execute(text("PRAGMA table_info(social_media_posts)")).fetchall()
            social_columns = [row[1] for row in result]
            
            if "usuario_id" not in social_columns:
                print("➕ Agregando usuario_id a social_media_posts...")
                conn.execute(text("ALTER TABLE social_media_posts ADD COLUMN usuario_id INTEGER"))
            
            conn.commit()
            print("✅ Todas las columnas verificadas/agregadas")
            
            # 4. Actualizar valores por defecto
            print("🔄 Actualizando valores por defecto...")
            conn.execute(text("UPDATE usuarios SET max_fuentes = 3, max_noticias_mes = 100, max_posts_social_mes = 500 WHERE plan = 'gratis' AND max_fuentes IS NULL"))
            conn.execute(text("UPDATE usuarios SET max_fuentes = NULL, max_noticias_mes = NULL, max_posts_social_mes = NULL WHERE plan = 'premium' AND max_fuentes IS NULL"))
            conn.commit()
            print("✅ Valores por defecto actualizados")
            
    except Exception as e:
        print(f"❌ Error solucionando columnas: {e}")

if __name__ == "__main__":
    fix_all_columns()