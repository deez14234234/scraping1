# app/scripts/diagnose_and_fix.py
from app.database import SessionLocal
from app.models import Usuario, Fuente, Noticia
from app.auth import get_password_hash

def diagnose_and_fix():
    """Diagnostica y soluciona todos los problemas del sistema."""
    print("🔍 DIAGNÓSTICO COMPLETO DEL SISTEMA")
    print("=" * 50)
    
    db = SessionLocal()
    try:
        # 1. VERIFICAR USUARIOS
        print("1. 📋 VERIFICANDO USUARIOS...")
        usuarios = db.query(Usuario).all()
        for usuario in usuarios:
            print(f"   👤 {usuario.email} - Plan: {usuario.plan} - Activo: {usuario.activo}")
            print(f"      Límites: fuentes={usuario.max_fuentes}, noticias={usuario.max_noticias_mes}")
        
        # 2. VERIFICAR FUENTES
        print("\n2. 🌐 VERIFICANDO FUENTES...")
        fuentes = db.query(Fuente).all()
        fuentes_sin_usuario = db.query(Fuente).filter(Fuente.usuario_id.is_(None)).count()
        print(f"   Total fuentes: {len(fuentes)}")
        print(f"   Fuentes sin usuario: {fuentes_sin_usuario}")
        
        for fuente in fuentes[:5]:  # Mostrar primeras 5
            usuario_nombre = fuente.usuario.email if fuente.usuario else "SIN USUARIO"
            print(f"   📰 {fuente.nombre} - Usuario: {usuario_nombre}")
        
        # 3. VERIFICAR NOTICIAS
        print("\n3. 📰 VERIFICANDO NOTICIAS...")
        total_noticias = db.query(Noticia).count()
        print(f"   Total noticias: {total_noticias}")
        
        # 4. SOLUCIONAR PROBLEMAS
        print("\n4. 🔧 SOLUCIONANDO PROBLEMAS...")
        
        # 4.1 Asignar fuentes al admin
        admin = db.query(Usuario).filter(Usuario.email == "admin@nexnews.com").first()
        if admin and fuentes_sin_usuario > 0:
            print(f"   ➕ Asignando {fuentes_sin_usuario} fuentes al admin...")
            db.query(Fuente).filter(Fuente.usuario_id.is_(None)).update(
                {"usuario_id": admin.id},
                synchronize_session=False
            )
            print(f"   ✅ {fuentes_sin_usuario} fuentes asignadas al admin")
        
        # 4.2 Verificar contraseña del admin
        if admin:
            # Si la contraseña no funciona, resetearla
            try:
                from app.auth import verify_password
                if not verify_password("admin123", admin.hashed_password):
                    print("   🔄 Resetear contraseña del admin...")
                    admin.hashed_password = get_password_hash("admin123")
                    print("   ✅ Contraseña del admin reseteada a 'admin123'")
            except Exception as e:
                print(f"   ⚠️  Error verificando contraseña: {e}")
        
        # 4.3 Actualizar límites de usuarios
        for usuario in usuarios:
            if usuario.plan == "premium" and usuario.max_fuentes is not None:
                usuario.max_fuentes = None
                usuario.max_noticias_mes = None
                usuario.max_posts_social_mes = None
                print(f"   ✅ Límites ilimitados para {usuario.email}")
            elif usuario.plan == "gratis" and (usuario.max_fuentes is None or usuario.max_fuentes != 3):
                usuario.max_fuentes = 3
                usuario.max_noticias_mes = 100
                usuario.max_posts_social_mes = 500
                print(f"   ✅ Límites actualizados para {usuario.email}")
        
        db.commit()
        
        # 5. VERIFICAR RESULTADO FINAL
        print("\n5. 📊 RESULTADO FINAL:")
        fuentes_admin = db.query(Fuente).filter(Fuente.usuario_id == admin.id).count() if admin else 0
        print(f"   ✅ Admin tiene {fuentes_admin} fuentes")
        print(f"   ✅ Total usuarios: {len(usuarios)}")
        print(f"   ✅ Total fuentes: {len(fuentes)}")
        
        print("\n🎉 DIAGNÓSTICO Y REPARACIÓN COMPLETADOS")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error en diagnóstico: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    diagnose_and_fix()