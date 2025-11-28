# app/database.py
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings

class Base(DeclarativeBase):
    pass

def _prepare_sqlite_path(db_url: str):
    """
    Si es SQLite de archivo, crea la carpeta contenedora si no existe.
    Acepta formatos:
      - sqlite:///./data/news.db
      - sqlite:///D:/Mineria/data/news.db
    """
    if not db_url.startswith("sqlite:///"):
        return

    # Extraer la ruta después de sqlite:///
    raw_path = db_url.replace("sqlite:///", "", 1)

    # Normalizar a slashes de Unix (SQLite los acepta en Windows)
    norm_path = raw_path.replace("\\", "/")

    # Ruta absoluta
    abs_path = os.path.abspath(norm_path)
    dir_path = os.path.dirname(abs_path)
    os.makedirs(dir_path, exist_ok=True)

# Preparar carpeta si es sqlite
_prepare_sqlite_path(settings.DATABASE_URL)

# Configuración del engine
engine_kwargs = dict(echo=False, pool_pre_ping=True, future=True)
if settings.DATABASE_URL.startswith("sqlite:///"):
    # Necesario cuando hay múltiples hilos / uvicorn reload
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def init_db():
    from app import models  # registra los modelos
    Base.metadata.create_all(bind=engine)
    _ensure_categoria_column()
    _ensure_usuario_fuente_relation()
    _ensure_usuario_columns()
    _ensure_social_media_columns()  # <- AGREGAR ESTA LÍNEA
    create_default_user()  # Crear usuario por defecto después de crear tablas
    create_default_benefits()  # Crear beneficios por defecto

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def health_check_db():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))

# -----------------------------
# Función extra: asegurar columna 'categoria'
# -----------------------------
def _ensure_categoria_column():
    """Agrega la columna 'categoria' a la tabla 'noticias' si no existe."""
    with engine.connect() as conn:
        # Verificar si columna existe
        result = conn.execute(text("PRAGMA table_info(noticias)")).all()
        columnas = [row[1] for row in result]  # fila[1] es el nombre de la columna
        if "categoria" not in columnas:
            print("[INFO] Columna 'categoria' no existe. Se creará automáticamente.")
            conn.execute(text("ALTER TABLE noticias ADD COLUMN categoria VARCHAR(255)"))
            conn.execute(text("UPDATE noticias SET categoria = 'General' WHERE categoria IS NULL"))
            conn.commit()
            print("[OK] Columna 'categoria' agregada y noticias existentes actualizadas.")
        else:
            print("[OK] Columna 'categoria' ya existe.")

# -----------------------------
# Función para asegurar relación usuario-fuente
# -----------------------------
def _ensure_usuario_fuente_relation():
    """Agrega la columna 'usuario_id' a la tabla 'fuentes' si no existe."""
    with engine.connect() as conn:
        # Verificar si columna existe
        result = conn.execute(text("PRAGMA table_info(fuentes)")).all()
        columnas = [row[1] for row in result]  # fila[1] es el nombre de la columna
        
        if "usuario_id" not in columnas:
            print("[INFO] Columna 'usuario_id' no existe en 'fuentes'. Se creará automáticamente.")
            conn.execute(text("ALTER TABLE fuentes ADD COLUMN usuario_id INTEGER"))
            conn.commit()
            print("[OK] Columna 'usuario_id' agregada a tabla 'fuentes'.")
            
            # Asignar fuentes existentes al usuario admin si existe
            try:
                user_result = conn.execute(text("SELECT id FROM usuarios WHERE email = 'admin@nexnews.com'")).fetchone()
                if user_result:
                    admin_id = user_result[0]
                    conn.execute(text("UPDATE fuentes SET usuario_id = ? WHERE usuario_id IS NULL"), (admin_id,))
                    conn.commit()
                    print(f"[OK] Fuentes existentes asignadas al usuario admin (ID: {admin_id})")
            except Exception as e:
                print(f"[INFO] No se pudieron asignar fuentes existentes: {e}")
        else:
            print("[OK] Columna 'usuario_id' ya existe en 'fuentes'.")

# -----------------------------
# Función para crear usuario por defecto
# -----------------------------
def create_default_user():
    """Crea un usuario administrador por defecto si no existe."""
    # Importar aquí para evitar circular imports
    from app.auth import get_password_hash
    from app.models import Usuario
    
    db = SessionLocal()
    try:
        # Verificar si ya existe el usuario
        user = db.query(Usuario).filter(Usuario.email == "admin@nexnews.com").first()
        if not user:
            hashed_password = get_password_hash("Admin123!")
            new_user = Usuario(
                email="admin@nexnews.com",
                nombre="Administrador",
                hashed_password=hashed_password,
                plan="premium",
                activo=True,
                is_admin=True,
                max_fuentes=None,  # Ilimitado para premium
                max_noticias_mes=None,
                max_posts_social_mes=None
            )
            db.add(new_user)
            db.commit()
            print("✅ Usuario admin premium creado:")
            print("   Email: admin@nexnews.com")
            print("   Password: Admin123!")
            print("   Plan: Premium (límites ilimitados)")
        else:
            # Actualizar usuario existente si es necesario
            if user.plan == "gratis":
                user.plan = "premium"
                user.is_admin = True
                user.max_fuentes = None
                user.max_noticias_mes = None
                user.max_posts_social_mes = None
                db.commit()
                print("✅ Usuario admin actualizado a plan Premium")
            else:
                print("✅ Usuario admin premium ya existe")
                
    except Exception as e:
        print(f"❌ Error creando usuario admin: {e}")
        # Intentar con contraseña más corta como fallback
        try:
            db.rollback()
            user = db.query(Usuario).filter(Usuario.email == "admin@nexnews.com").first()
            if not user:
                hashed_password = get_password_hash("admin123")
                new_user = Usuario(
                    email="admin@nexnews.com",
                    nombre="Administrador", 
                    hashed_password=hashed_password,
                    plan="premium",
                    activo=True,
                    max_fuentes=None,
                    max_noticias_mes=None,
                    max_posts_social_mes=None
                )
                db.add(new_user)
                db.commit()
                print("✅ Usuario creado con contraseña alternativa:")
                print("   Email: admin@nexnews.com")
                print("   Password: admin123")
                print("   Plan: Premium")
        except Exception as e2:
            print(f"❌ Error incluso con contraseña alternativa: {e2}")
    finally:
        db.close()

# -----------------------------
# Función para crear beneficios por defecto
# -----------------------------
def create_default_benefits():
    """Crea los beneficios de planes por defecto si no existen."""
    from app.models import PlanBeneficio
    
    db = SessionLocal()
    try:
        # Verificar si ya existen beneficios
        existing_benefits = db.query(PlanBeneficio).count()
        if existing_benefits > 0:
            print(f"✅ Ya existen {existing_benefits} beneficios de planes")
            return
        
        beneficios = [
            # NOTICIAS
            {"plan": "ambos", "categoria": "noticias", "caracteristica": "Límite mensual de noticias", 
             "valor_gratis": "100", "valor_premium": "Ilimitadas", "ilimitado_premium": True, "orden": 1},
            
            {"plan": "ambos", "categoria": "noticias", "caracteristica": "Fuentes de noticias", 
             "valor_gratis": "3", "valor_premium": "Ilimitadas", "ilimitado_premium": True, "orden": 2},
            
            {"plan": "ambos", "categoria": "noticias", "caracteristica": "Frecuencia de scraping", 
             "valor_gratis": "6 horas", "valor_premium": "30 minutos", "ilimitado_premium": False, "orden": 3},
            
            # REDES SOCIALES
            {"plan": "ambos", "categoria": "redes_sociales", "caracteristica": "Posts de redes/mes", 
             "valor_gratis": "500", "valor_premium": "10,000", "ilimitado_premium": False, "orden": 4},
            
            {"plan": "ambos", "categoria": "redes_sociales", "caracteristica": "Plataformas soportadas", 
             "valor_gratis": "3", "valor_premium": "Todas", "ilimitado_premium": True, "orden": 5},
            
            # EXPORTACIÓN
            {"plan": "ambos", "categoria": "exportacion", "caracteristica": "Formatos de exportación", 
             "valor_gratis": "CSV", "valor_premium": "CSV, Excel, JSON, PDF", "ilimitado_premium": False, "orden": 6},
            
            {"plan": "ambos", "categoria": "exportacion", "caracteristica": "Exportaciones/mes", 
             "valor_gratis": "1", "valor_premium": "Ilimitadas", "ilimitado_premium": True, "orden": 7},
            
            # ALMACENAMIENTO
            {"plan": "ambos", "categoria": "almacenamiento", "caracteristica": "Retención de datos", 
             "valor_gratis": "30 días", "valor_premium": "2 años", "ilimitado_premium": False, "orden": 8},
            
            {"plan": "ambos", "categoria": "almacenamiento", "caracteristica": "Almacenamiento", 
             "valor_gratis": "100MB", "valor_premium": "10GB", "ilimitado_premium": False, "orden": 9},
            
            # FUNCIONALIDADES AVANZADAS (Exclusivas Premium)
            {"plan": "premium", "categoria": "analisis", "caracteristica": "Análisis de sentimiento", 
             "valor_gratis": "❌ No", "valor_premium": "✅ Sí", "ilimitado_premium": False, "es_exclusivo": True, "orden": 10},
            
            {"plan": "premium", "categoria": "analisis", "caracteristica": "Alertas inteligentes", 
             "valor_gratis": "❌ No", "valor_premium": "✅ Sí", "ilimitado_premium": False, "es_exclusivo": True, "orden": 11},
            
            {"plan": "ambos", "categoria": "api", "caracteristica": "API requests/día", 
             "valor_gratis": "100", "valor_premium": "10,000", "ilimitado_premium": False, "es_exclusivo": False, "orden": 12},
            
            {"plan": "premium", "categoria": "api", "caracteristica": "Webhooks", 
             "valor_gratis": "❌ No", "valor_premium": "✅ Sí", "ilimitado_premium": False, "es_exclusivo": True, "orden": 13},
            
            {"plan": "premium", "categoria": "reportes", "caracteristica": "Reportes automáticos", 
             "valor_gratis": "❌ No", "valor_premium": "✅ Sí", "ilimitado_premium": False, "es_exclusivo": True, "orden": 14},
            
            # SOPORTE
            {"plan": "ambos", "categoria": "soporte", "caracteristica": "Soporte", 
             "valor_gratis": "Documentación", "valor_premium": "24/7 Prioritario", "ilimitado_premium": False, "orden": 15},
            
            {"plan": "ambos", "categoria": "soporte", "caracteristica": "SLA disponibilidad", 
             "valor_gratis": "Mejor esfuerzo", "valor_premium": "99.9%", "ilimitado_premium": False, "orden": 16},
        ]
        
        for beneficio in beneficios:
            nuevo_beneficio = PlanBeneficio(**beneficio)
            db.add(nuevo_beneficio)
        
        db.commit()
        print(f"✅ {len(beneficios)} beneficios de planes creados exitosamente")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error creando beneficios: {e}")
    finally:
        db.close()

# -----------------------------
# Función para verificar estado de la base de datos
# -----------------------------
# En app/database.py - CORREGIR la función check_database_status
def check_database_status():
    """Verifica el estado de la base de datos y muestra información."""
    from app.models import Usuario, Fuente, Noticia, PlanBeneficio
    from sqlalchemy import func  # ✅ AGREGAR ESTA IMPORTACIÓN
    
    try:
        db = SessionLocal()
        
        # Contar registros
        user_count = db.query(Usuario).count()
        fuente_count = db.query(Fuente).count()
        noticia_count = db.query(Noticia).count()
        benefit_count = db.query(PlanBeneficio).count()
        
        # Contar fuentes por usuario
        fuentes_por_usuario = db.query(
            Usuario.email, 
            func.count(Fuente.id).label('total_fuentes')
        ).join(Fuente, Usuario.id == Fuente.usuario_id, isouter=True
        ).group_by(Usuario.id).all()
        
        # Verificar tablas existentes
        if settings.DATABASE_URL.startswith("sqlite:///"):
            tables = db.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
        else:
            # Para PostgreSQL/MySQL
            tables = db.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")).fetchall()
        
        table_names = [table[0] for table in tables]
        
        print("=" * 60)
        print("📊 ESTADO DE LA BASE DE DATOS")
        print("=" * 60)
        print(f"📍 URL: {settings.DATABASE_URL}")
        print(f"📋 Tablas: {len(table_names)}")
        print(f"👥 Usuarios registrados: {user_count}")
        print(f"🌐 Fuentes: {fuente_count}")
        print(f"📰 Noticias: {noticia_count}")
        print(f"💎 Beneficios de planes: {benefit_count}")
        print("")
        
        # Mostrar distribución de fuentes por usuario
        if fuentes_por_usuario:
            print("📊 DISTRIBUCIÓN DE FUENTES POR USUARIO:")
            for usuario, total in fuentes_por_usuario:
                plan_usuario = db.query(Usuario.plan).filter(Usuario.email == usuario).scalar()
                print(f"   • {usuario} ({plan_usuario}): {total} fuentes")
        
        print("")
        print("🗃️ TABLAS ENCONTRADAS:")
        for table in sorted(table_names):
            print(f"   • {table}")
        
        print("=" * 60)
        
        db.close()
        return True
        
    except Exception as e:
        print(f"❌ Error verificando estado de la base de datos: {e}")
        return False
# En app/database.py - AGREGAR esta función
def _ensure_social_media_columns():
    """Agrega las columnas faltantes a la tabla social_media_posts."""
    with engine.connect() as conn:
        # Verificar columnas existentes
        result = conn.execute(text("PRAGMA table_info(social_media_posts)")).fetchall()
        existing_columns = [row[1] for row in result]
        
        # Columnas que deben existir
        required_columns = ["usuario_id"]
        
        for column_name in required_columns:
            if column_name not in existing_columns:
                print(f"[INFO] Columna '{column_name}' no existe en social_media_posts. Se creará automáticamente.")
                conn.execute(text(f"ALTER TABLE social_media_posts ADD COLUMN {column_name} INTEGER"))
                print(f"[OK] Columna '{column_name}' agregada a social_media_posts")
        
        conn.commit()

def _ensure_usuario_columns():
    """Agrega las columnas de límites a la tabla usuarios si no existen."""
    with engine.connect() as conn:
        # Verificar columnas existentes
        result = conn.execute(text("PRAGMA table_info(usuarios)")).fetchall()
        existing_columns = [row[1] for row in result]
        
        columns_to_add = [
            ("max_fuentes", "INTEGER"),
            ("max_noticias_mes", "INTEGER"),
            ("max_posts_social_mes", "INTEGER"),
            ("plan_trial_start", "TIMESTAMP"),
            ("plan_trial_expires", "TIMESTAMP"),
            ("plan_trial_reminder_sent", "TIMESTAMP"),
            ("is_admin", "INTEGER")
        ]
        
        for column_name, column_type in columns_to_add:
            if column_name not in existing_columns:
                print(f"[INFO] Columna '{column_name}' no existe. Se creará automáticamente.")
                conn.execute(text(f"ALTER TABLE usuarios ADD COLUMN {column_name} {column_type}"))
                print(f"[OK] Columna '{column_name}' agregada")
        
        conn.commit()
        
        # Actualizar valores por defecto
        conn.execute(text("UPDATE usuarios SET max_fuentes = 3, max_noticias_mes = 100, max_posts_social_mes = 500 WHERE plan = 'gratis' AND max_fuentes IS NULL"))
        conn.execute(text("UPDATE usuarios SET max_fuentes = NULL, max_noticias_mes = NULL, max_posts_social_mes = NULL WHERE plan = 'premium' AND max_fuentes IS NULL"))
        # Asegurar que si existe admin@nexnews.com se marque como is_admin
        try:
            conn.execute(text("UPDATE usuarios SET is_admin = 1 WHERE email = 'admin@nexnews.com'"))
        except Exception:
            pass
        conn.commit()
# -----------------------------
# Función para migrar datos existentes
# -----------------------------
def migrate_existing_data():
    """Migra datos existentes al nuevo sistema con relaciones usuario-fuente."""
    from app.models import Usuario, Fuente
    
    db = SessionLocal()
    try:
        print("🔄 Migrando datos existentes...")
        
        # Obtener usuario admin
        admin = db.query(Usuario).filter(Usuario.email == "admin@nexnews.com").first()
        if not admin:
            print("❌ No se encontró usuario admin para migración")
            return
        
        # Contar fuentes sin usuario asignado
        fuentes_sin_usuario = db.query(Fuente).filter(Fuente.usuario_id.is_(None)).count()
        
        if fuentes_sin_usuario > 0:
            print(f"📦 Asignando {fuentes_sin_usuario} fuentes al usuario admin...")
            
            # Asignar todas las fuentes sin usuario al admin
            db.query(Fuente).filter(Fuente.usuario_id.is_(None)).update(
                {"usuario_id": admin.id},
                synchronize_session=False
            )
            db.commit()
            print(f"✅ {fuentes_sin_usuario} fuentes asignadas al usuario admin")
        else:
            print("✅ Todas las fuentes ya tienen usuario asignado")
            
        # Verificar usuarios gratis y actualizar sus límites
        usuarios_gratis = db.query(Usuario).filter(Usuario.plan == "gratis").all()
        for usuario in usuarios_gratis:
            if usuario.max_fuentes is None or usuario.max_fuentes != 3:
                usuario.max_fuentes = 3
                usuario.max_noticias_mes = 100
                usuario.max_posts_social_mes = 500
                print(f"✅ Actualizados límites para usuario gratis: {usuario.email}")
        
        db.commit()
        print("🎉 Migración de datos completada")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error en migración: {e}")
    finally:
        db.close()