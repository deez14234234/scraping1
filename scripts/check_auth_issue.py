# app/scripts/check_auth_issue.py
from app.database import SessionLocal
from app.models import Usuario

def check_auth_issue():
    """Verifica el problema específico de autenticación."""
    print("🔍 VERIFICANDO PROBLEMA DE AUTENTICACIÓN")
    print("=" * 50)
    
    db = SessionLocal()
    try:
        # Verificar usuarios
        usuarios = db.query(Usuario).all()
        print("👥 USUARIOS EN SISTEMA:")
        for usuario in usuarios:
            print(f"   • {usuario.email} - Plan: {usuario.plan} - Activo: {usuario.activo}")
            print(f"      Contraseña hash: {usuario.hashed_password[:20]}...")
        
        # Verificar usuario admin específicamente
        admin = db.query(Usuario).filter(Usuario.email == "admin@nexnews.com").first()
        if admin:
            print(f"\n👑 USUARIO ADMIN:")
            print(f"   ID: {admin.id}")
            print(f"   Email: {admin.email}")
            print(f"   Plan: {admin.plan}")
            print(f"   Activo: {admin.activo}")
            print(f"   Límites: fuentes={admin.max_fuentes}, noticias={admin.max_noticias_mes}")
            
            # Verificar si puede hacer login
            from app.auth import verify_password
            test_passwords = ["admin123", "Admin123!", "admin"]
            
            for pwd in test_passwords:
                try:
                    if verify_password(pwd, admin.hashed_password):
                        print(f"   ✅ Contraseña correcta: '{pwd}'")
                        break
                except:
                    continue
            else:
                print("   ❌ Ninguna contraseña de prueba funciona")
        
        print("\n🎯 POSIBLES SOLUCIONES:")
        print("   1. Verificar que el JavaScript esté enviando el token")
        print("   2. Verificar que las rutas web tengan la dependencia de autenticación")
        print("   3. Resetear contraseña del admin si es necesario")
        
    except Exception as e:
        print(f"❌ Error en verificación: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    check_auth_issue()