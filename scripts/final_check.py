# app/scripts/final_check.py
from app.database import SessionLocal
from app.models import Usuario, Fuente

def final_check():
    """Verificación final del sistema."""
    print("✅ VERIFICACIÓN FINAL DEL SISTEMA")
    print("=" * 40)
    
    db = SessionLocal()
    try:
        # 1. Usuarios y sus fuentes
        usuarios = db.query(Usuario).all()
        print("👥 USUARIOS Y SUS FUENTES:")
        for usuario in usuarios:
            fuentes_count = db.query(Fuente).filter(Fuente.usuario_id == usuario.id).count()
            print(f"   • {usuario.email} ({usuario.plan}): {fuentes_count} fuentes")
        
        # 2. Fuentes totales
        total_fuentes = db.query(Fuente).count()
        print(f"\n🌐 TOTAL FUENTES: {total_fuentes}")
        
        # 3. Verificar que admin tenga fuentes
        admin = db.query(Usuario).filter(Usuario.email == "admin@nexnews.com").first()
        if admin:
            admin_fuentes = db.query(Fuente).filter(Fuente.usuario_id == admin.id).count()
            print(f"👑 ADMIN: {admin_fuentes}/{total_fuentes} fuentes")
            
            if admin_fuentes == total_fuentes:
                print("🎉 ✅ SISTEMA LISTO - Todas las fuentes asignadas al admin")
            else:
                print("⚠️  Algunas fuentes no están asignadas")
        
        print("\n🚀 El sistema debería funcionar correctamente ahora")
        
    except Exception as e:
        print(f"❌ Error en verificación final: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    final_check()