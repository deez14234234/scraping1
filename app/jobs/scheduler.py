# app/jobs/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Fuente, Usuario
from app.scraper.generic import GenericScraper
from app.scraper.base import BaseScraper
from app.services.source_service import mark_scraped
import asyncio
import logging
from app.config import settings
import smtplib
from email.message import EmailMessage

log = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None

async def _scrape_fuentes_usuario(db: Session, usuario_id: int):
    """Scrapea las fuentes permitidas para un usuario específico según su plan."""
    try:
        usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
        if not usuario or not usuario.activo:
            log.warning(f"Usuario {usuario_id} no encontrado o inactivo")
            return

        # Obtener scraper base para verificar límites
        scraper_base = BaseScraper()
        fuentes_permitidas = scraper_base.obtener_fuentes_permitidas(db, usuario_id)
        
        if not fuentes_permitidas:
            log.info(f"🔒 Usuario {usuario.email} no tiene fuentes permitidas para scrapear")
            return

        plan_info = "Premium" if usuario.plan == "premium" else f"Gratis ({len(fuentes_permitidas)}/{usuario.max_fuentes or 3} fuentes)"
        log.info(f"🔍 Scrapeando para {usuario.email} ({plan_info}): {len(fuentes_permitidas)} fuentes")

        for fuente in fuentes_permitidas:
            try:
                log.info(f"📰 Scrapeando: {fuente.nombre} - {fuente.url_listado}")
                scraper = GenericScraper(fuente.url_listado)
                articulos = scraper.scrape_and_store()
                
                # Marcar como scrapeada
                mark_scraped(db, fuente.id)
                
                log.info(f"✅ {fuente.nombre}: {len(articulos)} artículos procesados")
                
            except Exception as e:
                log.error(f"❌ Error scrapeando {fuente.nombre}: {e}")
                continue

    except Exception as e:
        log.error(f"💥 Error en scraping para usuario {usuario_id}: {e}")

async def _scrape_all_users():
    """Scraping automático para todos los usuarios activos respetando límites de planes."""
    print(f"🚀 Iniciando scraping automático - {datetime.now()}")
    
    db = SessionLocal()
    try:
        # Obtener todos los usuarios activos
        usuarios = db.query(Usuario).filter(Usuario.activo == True).all()
        print(f"👥 Usuarios activos: {len(usuarios)}")
        
        # Scrapear para cada usuario
        for usuario in usuarios:
            try:
                await _scrape_fuentes_usuario(db, usuario.id)
                print(f"✅ Scraping completado para usuario: {usuario.email}")
            except Exception as e:
                print(f"❌ Error con usuario {usuario.email}: {e}")
                continue
        
        print(f"🎯 Scraping automático completado - {datetime.now()}")
        
    except Exception as e:
        print(f"💥 Error general en scraping automático: {e}")
    finally:
        db.close()


def run_trial_reminder_now():
    """Ejecuta la misma lógica del job `trial_reminder_job` de forma síncrona y devuelve resumen.

    Esta función es pública a nivel de módulo para que otros módulos (ej. web) puedan llamarla.
    """
    db = SessionLocal()
    summary = {"checked": 0, "candidates": 0, "sent": 0, "errors": []}
    try:
        now = datetime.utcnow()
        remind_date = now + timedelta(days=3)
        candidats = db.query(Usuario).filter(
            Usuario.plan == "premium",
            Usuario.plan_trial_expires.isnot(None),
            Usuario.plan_trial_expires <= remind_date,
            Usuario.plan_trial_expires > now,
            Usuario.plan_trial_reminder_sent.is_(None)
        ).all()

        summary["checked"] = 1
        summary["candidates"] = len(candidats)

        for u in candidats:
            try:
                subject = "Tu trial Premium expira en 3 días"
                body = f"Hola {u.nombre or u.email},\n\nTu trial Premium expirará el {u.plan_trial_expires}.\nSi deseas continuar con Premium, realiza la renovación antes de esa fecha.\n\nSaludos,\nEquipo NexNews"

                sent = False
                if getattr(settings, 'SMTP_HOST', None) and getattr(settings, 'EMAIL_ENABLED', False):
                    try:
                        msg = EmailMessage()
                        msg['Subject'] = subject
                        msg['From'] = getattr(settings, 'SMTP_FROM', 'noreply@nexnews.com')
                        msg['To'] = u.email
                        msg.set_content(body)

                        with smtplib.SMTP(getattr(settings, 'SMTP_HOST'), getattr(settings, 'SMTP_PORT', 25)) as smtp:
                            if getattr(settings, 'SMTP_STARTTLS', False):
                                smtp.starttls()
                            if getattr(settings, 'SMTP_USER', None):
                                smtp.login(getattr(settings, 'SMTP_USER'), getattr(settings, 'SMTP_PASSWORD'))
                            smtp.send_message(msg)
                        sent = True
                    except Exception as e:
                        log.error(f"❌ Error sending SMTP reminder to {u.email}: {e}")

                if not sent:
                    log.info(f"[TRIAL-REMINDER] To: {u.email} | Subject: {subject} | Body: {body}")

                u.plan_trial_reminder_sent = datetime.utcnow()
                db.add(u)
                db.commit()
                summary["sent"] += 1
            except Exception as e:
                db.rollback()
                log.error(f"❌ Error processing reminder for {u.email}: {e}")
                summary["errors"].append(str(e))
    except Exception as e:
        log.error(f"💥 Error running trial reminders now: {e}")
        summary["errors"].append(str(e))
    finally:
        db.close()
    return summary

def _scrape_all_sources_legacy():
    """Función legacy para compatibilidad (sin límites de usuario)"""
    print(f"🚀 Iniciando scraping legacy - {datetime.now()}")
    db = SessionLocal()
    try:
        fuentes = db.scalars(select(Fuente).where(Fuente.habilitada == True)).all()  # noqa: E712
        print(f"📰 Fuentes habilitadas: {len(fuentes)}")
        
        for f in fuentes:
            try:
                print(f"🔍 Scrapeando: {f.url_listado}")
                scraper = GenericScraper(f.url_listado)
                articulos = scraper.scrape_and_store()
                print(f"✅ {f.url_listado}: {len(articulos)} artículos procesados")
                mark_scraped(db, f.id)
            except Exception as e:
                print(f"❌ Error con {f.url_listado}: {e}")
    finally:
        db.close()
    print(f"🎯 Scraping legacy completado - {datetime.now()}")

def start_scheduler():
    """Inicia el scheduler con scraping automático que respeta límites de planes."""
    global _scheduler
    if _scheduler:
        return
    
    _scheduler = AsyncIOScheduler()
    
    # ✅ SCRAPING AUTOMÁTICO CADA 2 HORAS (RESPETANDO LÍMITES)
    @_scheduler.scheduled_job("interval", minutes=120, id="scraping_automatico")
    def periodic_scrape():
        """Trabajo programado que respeta límites por usuario."""
        try:
            # Ejecutar en el event loop
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Si el loop está corriendo, crear task
                asyncio.create_task(_scrape_all_users())
            else:
                # Si no, ejecutar directamente
                loop.run_until_complete(_scrape_all_users())
        except Exception as e:
            log.error(f"💥 Error en job programado: {e}")

    # ✅ SCRAPING RÁPIDO CADA 30 MINUTOS (SOLO PREMIUM) - OPCIONAL
    @_scheduler.scheduled_job("interval", minutes=30, id="scraping_rapido")
    def periodic_fast_scrape():
        """Scraping rápido cada 30 minutos solo para usuarios premium."""
        try:
            db = SessionLocal()
            try:
                usuarios_premium = db.query(Usuario).filter(
                    Usuario.activo == True,
                    Usuario.plan == "premium"
                ).all()
                
                if usuarios_premium:
                    log.info(f"🚀 Scraping rápido para {len(usuarios_premium)} usuarios premium")
                    
                    for usuario in usuarios_premium:
                        asyncio.create_task(_scrape_fuentes_usuario(db, usuario.id))
                        
            finally:
                db.close()
                
        except Exception as e:
            log.error(f"💥 Error en scraping rápido: {e}")

    _scheduler.start()
    # ✅ JOB ADICIONAL: Verificar trials expirados cada 1 hora
    @_scheduler.scheduled_job("interval", minutes=60, id="check_trials_expiry")
    def periodic_check_trials():
        try:
            db = SessionLocal()
            try:
                now = datetime.utcnow()
                expired = db.query(Usuario).filter(
                    Usuario.plan == "premium",
                    Usuario.plan_trial_expires.isnot(None),
                    Usuario.plan_trial_expires <= now
                ).all()
                if expired:
                    log.info(f"🔔 Downgrading {len(expired)} users with expired trials")
                for u in expired:
                    try:
                        log.info(f"🔄 Downgrading user {u.email} - trial expired {u.plan_trial_expires}")
                        u.plan = "gratis"
                        u.max_fuentes = 3
                        u.max_noticias_mes = 300
                        u.max_posts_social_mes = 500
                        u.plan_trial_start = None
                        u.plan_trial_expires = None
                        db.add(u)
                        db.commit()
                    except Exception as e:
                        db.rollback()
                        log.error(f"❌ Error downgrading user {u.email}: {e}")
            finally:
                db.close()
        except Exception as e:
            log.error(f"💥 Error checking trials expiry: {e}")
    
    # ✅ JOB ADICIONAL: Enviar recordatorios de trial 3 días antes de expirar
    @_scheduler.scheduled_job("interval", minutes=60, id="trial_reminder_job")
    def periodic_trial_reminder():
        try:
            db = SessionLocal()
            try:
                now = datetime.utcnow()
                remind_date = now + timedelta(days=3)
                # Buscar usuarios con trial que expira dentro de ~3 días y que no han recibido recordatorio
                candidats = db.query(Usuario).filter(
                    Usuario.plan == "premium",
                    Usuario.plan_trial_expires.isnot(None),
                    Usuario.plan_trial_expires <= remind_date,
                    Usuario.plan_trial_expires > now,
                    Usuario.plan_trial_reminder_sent.is_(None)
                ).all()

                if not candidats:
                    return

                for u in candidats:
                    try:
                        # Preparar mensaje
                        subject = "Tu trial Premium expira en 3 días"
                        body = f"Hola {u.nombre or u.email},\n\nTu trial Premium expirará el {u.plan_trial_expires}.\nSi deseas continuar con Premium, realiza la renovación antes de esa fecha.\n\nSaludos,\nEquipo NexNews"

                        sent = False
                        if getattr(settings, 'SMTP_HOST', None):
                            try:
                                msg = EmailMessage()
                                msg['Subject'] = subject
                                msg['From'] = getattr(settings, 'SMTP_FROM', 'noreply@nexnews.com')
                                msg['To'] = u.email
                                msg.set_content(body)

                                with smtplib.SMTP(getattr(settings, 'SMTP_HOST'), getattr(settings, 'SMTP_PORT', 25)) as smtp:
                                    if getattr(settings, 'SMTP_STARTTLS', False):
                                        smtp.starttls()
                                    if getattr(settings, 'SMTP_USER', None):
                                        smtp.login(getattr(settings, 'SMTP_USER'), getattr(settings, 'SMTP_PASSWORD'))
                                    smtp.send_message(msg)
                                sent = True
                            except Exception as e:
                                log.error(f"❌ Error sending SMTP reminder to {u.email}: {e}")

                        if not sent:
                            log.info(f"[TRIAL-REMINDER] To: {u.email} | Subject: {subject} | Body: {body}")

                        # Marcar recordatorio enviado
                        u.plan_trial_reminder_sent = datetime.utcnow()
                        db.add(u)
                        db.commit()
                    except Exception as e:
                        db.rollback()
                        log.error(f"❌ Error processing reminder for {u.email}: {e}")
            finally:
                db.close()
        except Exception as e:
            log.error(f"💥 Error in trial reminder job: {e}")
    
        # NOTE: run_trial_reminder_now existe también como función pública definida más arriba
    print("=" * 60)
    print("✅ SCHEDULER INICIADO")
    print("📍 Scraping automático cada 2 horas (todos los usuarios)")
    print("📍 Scraping rápido cada 30 minutos (solo premium)")
    print("🔒 Respetando límites de planes:")
    print("   • Gratis: 3 fuentes máximas")
    print("   • Premium: Fuentes ilimitadas")
    print("=" * 60)

def stop_scheduler():
    """Detiene el scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        _scheduler = None
        print("🛑 Scheduler detenido")

async def scrapear_usuario_manual(usuario_id: int):
    """Función para scraping manual de un usuario específico."""
    db = SessionLocal()
    try:
        await _scrape_fuentes_usuario(db, usuario_id)
    finally:
        db.close()

async def scrapear_fuente_manual(usuario_id: int, fuente_id: int) -> bool:
    """Función para scraping manual de una fuente específica con verificación de permisos."""
    db = SessionLocal()
    try:
        scraper_base = BaseScraper()
        
        # Verificar permisos primero
        if not scraper_base.verificar_limite_fuentes_usuario(db, usuario_id, fuente_id):
            log.error(f"Usuario {usuario_id} no tiene permiso para scrapear fuente {fuente_id}")
            return False
        
        # Obtener la fuente
        fuente = db.query(Fuente).filter(Fuente.id == fuente_id).first()
        if not fuente:
            log.error(f"Fuente {fuente_id} no encontrada")
            return False
        
        # Scrapear la fuente
        try:
            log.info(f"🔍 Scrapeando manualmente: {fuente.nombre}")
            scraper = GenericScraper(fuente.url_listado)
            articulos = scraper.scrape_and_store()
            mark_scraped(db, fuente.id)
            log.info(f"✅ {fuente.nombre}: {len(articulos)} artículos procesados")
            return True
            
        except Exception as e:
            log.error(f"❌ Error scrapeando {fuente.nombre}: {e}")
            return False
            
    finally:
        db.close()