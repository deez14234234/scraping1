# app/scripts/update_user_limits.py
from app.database import SessionLocal
from app.models import Usuario

def update_user_limits():
    """Actualiza los límites de los usuarios según su plan."""
    print("🔄 ACTUALIZANDO LÍMITES DE USUARIOS...")
    
    db = SessionLocal()
    try:
        # Usuario gratis: establecer límites
        usuario_gratis = db.query(Usuario).filter(Usuario.plan == "gratis").first()
        if usuario_gratis:
            usuario_gratis.max_fuentes = 3
            usuario_gratis.max_noticias_mes = 100
            usuario_gratis.max_posts_social_mes = 500
            print(f"✅ Límites actualizados para usuario gratis: {usuario_gratis.email}")
        
        # Usuario premium: límites ilimitados
        usuario_premium = db.query(Usuario).filter(Usuario.plan == "premium").first()
        if usuario_premium:
            usuario_premium.max_fuentes = None
            usuario_premium.max_noticias_mes = None
            usuario_premium.max_posts_social_mes = None
            print(f"✅ Límites actualizados para usuario premium: {usuario_premium.email}")
        
        db.commit()
        print("🎉 Límites de usuarios actualizados")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error actualizando límites: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    update_user_limits()