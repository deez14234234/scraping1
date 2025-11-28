# app/scripts/reset_admin_password.py
from app.database import SessionLocal
from app.models import Usuario
from app.auth import get_password_hash

def reset_admin_password():
    """Resetea la contraseña del usuario admin."""
    print("🔄 RESETEANDO CONTRASEÑA DEL ADMIN...")
    
    db = SessionLocal()
    try:
        admin = db.query(Usuario).filter(Usuario.email == "admin@nexnews.com").first()
        if admin:
            # Resetear a una contraseña simple
            admin.hashed_password = get_password_hash("admin123")
            db.commit()
            print("✅ Contraseña del admin reseteada a 'admin123'")
        else:
            print("❌ No se encontró el usuario admin")
            
    except Exception as e:
        db.rollback()
        print(f"❌ Error reseteando contraseña: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    reset_admin_password()