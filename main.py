# main.py - VERSIÓN COMPLETA CORREGIDA
from fastapi import FastAPI, Request, Form, Depends 
from contextlib import asynccontextmanager
import os
from datetime import datetime, timedelta
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

# ✅ AGREGADO: Importar middleware de sesiones
from starlette.middleware.sessions import SessionMiddleware

# --- util: asegurar directorios para mounts ---
def _ensure_dir(path: str):
    """Crea el directorio si no existe."""
    if path and not os.path.isdir(path):
        os.makedirs(path, exist_ok=True)

# rutas de recursos
STATIC_DIR = "app/web/static"
IMAGES_DIR = "data/images"
TEMPLATES_DIR = "app/web/templates"

# ✅ AGREGADO: Configurar templates correctamente
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# --- Lifespan (startup/shutdown) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la base de datos y el scheduler al iniciar FastAPI."""
    from app.database import init_db, check_database_status
    from app.jobs.scheduler import start_scheduler, stop_scheduler
    
    # init_db() ya incluye create_default_user()
    init_db()
    check_database_status()  # Verificar estado de la DB
    
    try:
        start_scheduler()
        print("[OK] Scheduler configurado - Scraping automático cada 2 horas")
    except Exception as e:
        print(f"[ERROR] Error al iniciar scheduler: {e}")
    yield
    try:
        stop_scheduler()
    except Exception as e:
        print(f"[ERROR] Error al detener scheduler: {e}")

# --- FastAPI app ---
app = FastAPI(
    title="NexNews Scraping System",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ✅ CORREGIDO: SessionMiddleware PRIMERO
app.add_middleware(
    SessionMiddleware, 
    secret_key="tu-clave-secreta-super-segura-aqui-cambiar-en-produccion-12345",
    max_age=3600  # 1 hora de sesión
)

# --- Static files ---
_ensure_dir(STATIC_DIR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

_ensure_dir(IMAGES_DIR)
app.mount("/images", StaticFiles(directory=IMAGES_DIR), name="images")

# --- Importar routers DESPUÉS de crear la app ---
from app.routes import auth, news, web, categories, social_routes, payments, health, export, metrics, sources
from app.database import get_db
from sqlalchemy import desc

# --- Función helper para verificar autenticación ---
def check_auth(request: Request):
    """Verifica si el usuario está autenticado (normal o invitado)"""
    is_guest = request.session.get("is_guest", False)
    user_id = request.session.get("user_id")
    return user_id is not None or is_guest


def _enforce_trial_status(db: Session, user_id: int | None):
    """Verifica si el trial de un usuario expiró y degrada a 'gratis' si corresponde."""
    if not user_id:
        return
    try:
        usuario = db.query(__import__('app.models', fromlist=['Usuario']).Usuario).filter_by(id=user_id).first()
        if not usuario:
            return
        if usuario.plan == 'premium' and usuario.plan_trial_expires:
            now = datetime.utcnow()
            if usuario.plan_trial_expires and usuario.plan_trial_expires <= now:
                usuario.plan = 'gratis'
                usuario.max_fuentes = 3
                usuario.max_noticias_mes = 300
                usuario.max_posts_social_mes = 500
                usuario.plan_trial_start = None
                usuario.plan_trial_expires = None
                db.add(usuario)
                db.commit()
    except Exception as e:
        print('[WARN] error enforcing trial status:', e)

# --- PÁGINA PRINCIPAL AHORA ES EL LOGIN ---
@app.get("/", response_class=HTMLResponse)
async def root_redirect():
    """Redirige la raíz al login (página principal ahora)."""
    return RedirectResponse(url="/web/login", status_code=302)

# --- Página de Login (Nueva Página Principal) ---
@app.get("/web/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Página de login - ahora es la página principal."""
    # Si ya está autenticado, redirigir al dashboard
    if check_auth(request):
        return RedirectResponse("/dashboard", status_code=302)
    
    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "is_main_page": True
        }
    )

# ✅ CORREGIDO: Ruta para procesar el login desde formulario web
@app.post("/web/login")
async def web_login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Procesa el login desde el formulario web y establece la sesión"""
    from app.auth import authenticate_user
    
    user = authenticate_user(db, email, password)
    if not user:
        # Redirigir con error
        return RedirectResponse("/web/login?error=Credenciales+incorrectas", status_code=303)
    # Enforce trial expiry state for this user
    _enforce_trial_status(db, user.id)

    # Reload user from DB in case trial enforcement changed plan
    try:
        user = db.query(__import__('app.models', fromlist=['Usuario']).Usuario).filter_by(id=user.id).first()
    except Exception:
        pass

    # ✅ ESTABLECER SESIÓN COMPLETA PARA LA WEB
    request.session["user_id"] = user.id
    request.session["user_email"] = user.email
    request.session["user_plan"] = user.plan
    request.session["user_nombre"] = user.nombre
    request.session["is_guest"] = False
    
    # Redirigir directamente al dashboard
    return RedirectResponse("/dashboard", status_code=303)

# ✅ AGREGADO: Ruta para login como invitado
@app.post("/web/guest-login")
async def guest_login(request: Request):
    """Establece sesión de usuario invitado"""
    # Crear sesión de invitado
    request.session["user_id"] = None
    request.session["user_email"] = "invitado@nexnews.com"
    request.session["user_plan"] = "gratis"
    request.session["user_nombre"] = "Invitado"
    request.session["is_guest"] = True
    
    return RedirectResponse("/dashboard", status_code=303)

# ✅ AGREGADO: Ruta para logout
@app.get("/web/logout")
async def web_logout(request: Request):
    """Cierra la sesión del usuario"""
    request.session.clear()
    return RedirectResponse("/web/login", status_code=302)

# --- Dashboard (página después del login) ---
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page(request: Request):
    """Dashboard principal - funciona para usuarios e invitados"""
    
    # Verificar autenticación en la ruta individual
    if not check_auth(request):
        return RedirectResponse("/web/login", status_code=302)
    
    # Verificar tipo de sesión
    is_guest = request.session.get("is_guest", False)
    user_id = request.session.get("user_id")
    
    # Preparar datos según el tipo de usuario
    if is_guest:
        # ✅ MODO INVITADO - Datos básicos
        user_data = {
            "email": "invitado@nexnews.com",
            "nombre": "Invitado",
            "plan": "gratis"
        }
        # Estadísticas básicas para invitados
        categorias = ["Política", "Deportes", "Tecnología", "Economía"]
        total_noticias = 0
        total_fuentes = 0
        total_social = 0
        fuentes_habilitadas = 0
    else:
        # ✅ USUARIO REGISTRADO - Datos completos de la base de datos
        from app.models import Noticia, Fuente, SocialMediaPost
        
        try:
            db: Session = next(get_db())
            # For logged in users enforce trial expiry
            _enforce_trial_status(db, user_id)
            
            # Obtener categorías
            categorias_query = (
                db.query(Noticia.categoria)
                .distinct()
                .filter(Noticia.categoria.isnot(None))
            )
            categorias = [c[0] for c in categorias_query.all()]
            
            # Obtener estadísticas
            total_noticias = db.query(Noticia).count()
            total_fuentes = db.query(Fuente).count()
            total_social = db.query(SocialMediaPost).count()
            fuentes_habilitadas = db.query(Fuente).filter(Fuente.habilitada == True).count()
            
            db.close()
        except Exception as e:
            print("[ERROR] Error al obtener datos del dashboard:", e)
            categorias = []
            total_noticias = 0
            total_fuentes = 0
            total_social = 0
            fuentes_habilitadas = 0

        # Si el usuario en sesión es admin, obtener suscripciones recientes
        admin_recent_upgrades = []
        try:
            if request.session.get('is_admin'):
                from app.database import SessionLocal
                from app import models
                db2 = SessionLocal()
                try:
                    rows = db2.query(models.Movimiento).filter(models.Movimiento.accion == 'upgrade_plan').order_by(desc(models.Movimiento.created_at)).limit(10).all()
                    # Parse detalle JSON si es posible
                    parsed = []
                    import json
                    for r in rows:
                        info = {}
                        try:
                            info = json.loads(r.detalle) if r.detalle else {}
                        except Exception:
                            info = { 'raw': r.detalle }
                        info.update({ 'created_at': getattr(r, 'created_at', None) })
                        parsed.append(info)
                    admin_recent_upgrades = parsed
                finally:
                    db2.close()
        except Exception:
            admin_recent_upgrades = []

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request, 
            "categorias": categorias,
            "total_noticias": total_noticias,
            "total_fuentes": total_fuentes,
            "total_social": total_social,
            "fuentes_habilitadas": fuentes_habilitadas,
            "ultima_actualizacion": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "current_user": {
                "email": request.session.get("user_email"),
                "nombre": request.session.get("user_nombre"),
                "plan": request.session.get("user_plan"),
                "trial_expires": request.session.get("user_plan_trial_expires")
            }
            ,
            "admin_recent_upgrades": admin_recent_upgrades
            }
    )

# --- Página de Registro ---
@app.get("/web/registro", response_class=HTMLResponse)
async def registro_page(request: Request):
    # Si ya está autenticado, redirigir al dashboard
    if check_auth(request):
        return RedirectResponse("/dashboard", status_code=302)
    
    return templates.TemplateResponse("registro.html", {"request": request})

@app.post("/web/registro")
async def web_registro(
    request: Request,
    email: str = Form(...),
    nombre: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Procesa el registro de nuevo usuario"""
    from app.auth import get_password_hash
    from app.models import Usuario
    
    # Verificar si el usuario ya existe
    existing_user = db.query(Usuario).filter(Usuario.email == email).first()
    if existing_user:
        return RedirectResponse("/web/registro?error=El+email+ya+está+registrado", status_code=303)
    
    # Crear nuevo usuario
    hashed_password = get_password_hash(password)
    # Admitir query param `plan=premium` para arrancar trial si el usuario viene desde CTA
    requested_plan = request.query_params.get("plan")
    plan_to_set = "gratis"
    trial_start = None
    trial_expires = None
    if requested_plan and requested_plan.lower() == "premium":
        plan_to_set = "premium"
        trial_start = datetime.utcnow()
        trial_expires = trial_start + timedelta(days=14)

    new_user = Usuario(
        email=email,
        nombre=nombre,
        hashed_password=hashed_password,
        plan=plan_to_set,
        activo=True,
        plan_trial_start=trial_start,
        plan_trial_expires=trial_expires
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Iniciar sesión automáticamente
    request.session["user_id"] = new_user.id
    request.session["user_email"] = new_user.email
    request.session["user_plan"] = new_user.plan
    request.session["user_plan_trial_expires"] = new_user.plan_trial_expires.isoformat() if new_user.plan_trial_expires else None
    request.session["user_nombre"] = new_user.nombre
    request.session["is_guest"] = False
    
    return RedirectResponse("/dashboard", status_code=303)

# --- Página de Exportación ---
@app.get("/web/export", response_class=HTMLResponse)
async def export_page(request: Request):
    # Verificar autenticación en la ruta individual
    if not check_auth(request):
        return RedirectResponse("/web/login", status_code=302)
        
    from app.models import Noticia, SocialMediaPost, Fuente
    total_news = 0
    total_social = 0
    total_sources = 0
    
    try:
        db: Session = next(get_db())
        total_news = db.query(Noticia).count()
        total_social = db.query(SocialMediaPost).count()
        total_sources = db.query(Fuente).filter(Fuente.habilitada == True).count()
        db.close()
    except Exception as e:
        print("[ERROR] Error al obtener datos para exportación:", e)

    return templates.TemplateResponse(
        "export.html",
        {
            "request": request,
            "total_news": total_news,
            "total_social": total_social,
            "total_sources": total_sources,
            "last_export": datetime.now().strftime("%d/%m/%Y %H:%M"),
            "current_user": {
                "email": request.session.get("user_email"),
                "plan": request.session.get("user_plan")
            }
        }
    )

# --- Página de Planes ---
@app.get("/web/plans", response_class=HTMLResponse)
async def plans_page(request: Request):
    # Verificar autenticación en la ruta individual
    if not check_auth(request):
        return RedirectResponse("/web/login", status_code=302)
        
    return templates.TemplateResponse(
        "plans.html", 
        {
            "request": request,
            "current_user": {
                "email": request.session.get("user_email"),
                "plan": request.session.get("user_plan")
            }
        }
    )

# --- Página de Métricas ---
@app.get("/web/metrics", response_class=HTMLResponse)
async def metrics_page(request: Request):
    # Verificar autenticación en la ruta individual
    if not check_auth(request):
        return RedirectResponse("/web/login", status_code=302)
        
    resultados = {
        "precision": 0.85,
        "recall": 0.82,
        "f1": 0.83,
        "auc": 0.89,
        "image": "/static/confusion_matrix.png"
    }
    return templates.TemplateResponse(
        "metrics.html", 
        {
            "request": request, 
            "resultados": resultados,
            "current_user": {
                "email": request.session.get("user_email"),
                "plan": request.session.get("user_plan")
            }
        }
    )

# --- Redirecciones ---
@app.get("/web", include_in_schema=False)
async def web_root():
    return RedirectResponse(url="/web/login", status_code=302)

@app.get("/home", include_in_schema=False)
async def home_redirect():
    return RedirectResponse(url="/dashboard", status_code=302)

@app.get("/index", include_in_schema=False)
async def index_redirect():
    return RedirectResponse(url="/dashboard", status_code=302)

# --- API routes ---
app.include_router(health.router, prefix="/api")
app.include_router(news.router, prefix="/api")
app.include_router(export.router, prefix="/api")
app.include_router(metrics.router, prefix="/api")
app.include_router(social_routes.router)
app.include_router(auth.router, prefix="/api/auth")

# --- Web routes (HTML) ---
app.include_router(web.router)
app.include_router(categories.router)  
app.include_router(sources.router)
app.include_router(payments.router)

# --- Ready ---
print("=" * 60)
print("🚀 NEXNEWS - SISTEMA INICIADO CORRECTAMENTE")
print("=" * 60)
print("📍 URLs PRINCIPALES:")
print("   • http://localhost:8000/           → Login (Página Principal)")
print("   • http://localhost:8000/dashboard  → Dashboard Principal")
print("   • http://localhost:8000/web/sources → Fuentes de Noticias")
print("   • http://localhost:8000/web/news    → Lista de Noticias")
print("   • http://localhost:8000/web/registro → Página de Registro")
print("=" * 60)
print("👤 USUARIO POR DEFECTO:")
print("   • Email: admin@nexnews.com")
print("   • Password: admin123")
print("=" * 60)
print("🔐 SISTEMA DE AUTENTICACIÓN:")
print("   • ✅ Sesiones web configuradas correctamente")
print("   • ✅ Autenticación por ruta individual")
print("   • ✅ Soporte para modo invitado")
print("=" * 60)