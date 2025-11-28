# app/models.py
from datetime import datetime
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Index, func, Boolean, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


# --- MODELO DE USUARIOS ---
class Usuario(Base):
    __tablename__ = "usuarios"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default="gratis")  # gratis, premium
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    ultimo_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    
    # Límites según plan (se pueden calcular o almacenar)
    max_fuentes: Mapped[int | None] = mapped_column(Integer, default=3)  # Gratis: 3, Premium: null (ilimitado)
    max_noticias_mes: Mapped[int | None] = mapped_column(Integer, default=100)  # Gratis: 100, Premium: null
    max_posts_social_mes: Mapped[int | None] = mapped_column(Integer, default=500)  # Gratis: 500, Premium: null
    # Trial / suscripción
    plan_trial_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    plan_trial_expires: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Recordar envíos de notificaciones del trial
    plan_trial_reminder_sent: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Flag admin
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    
    # Relaciones
    fuentes: Mapped[list["Fuente"]] = relationship("Fuente", back_populates="usuario")
    
    def puede_agregar_fuente(self, fuentes_actuales: int) -> bool:
        """Verifica si el usuario puede agregar más fuentes"""
        if self.plan == "premium":
            return True  # Ilimitado
        return fuentes_actuales < (self.max_fuentes or 3)
        
    def puede_scrapear_fuente(self, fuente_id: int, fuentes_habilitadas: list["Fuente"]) -> bool:
        """Verifica si el usuario puede scrapear una fuente específica"""
        if self.plan == "premium":
            return True  # Puede scrapear todas
        # Gratis solo puede scrapear sus primeras X fuentes
        max_fuentes = self.max_fuentes or 3
        return fuente_id in [f.id for f in fuentes_habilitadas[:max_fuentes]]
    
    def __repr__(self):
        return f"<Usuario {self.email} - {self.plan}>"


# --- MODELO DE FUENTES ---
class Fuente(Base):
    __tablename__ = "fuentes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url_listado: Mapped[str] = mapped_column(String(1000), unique=True, index=True)
    nombre: Mapped[str | None] = mapped_column(String(255), nullable=True)
    habilitada: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relación con usuario
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey('usuarios.id'), nullable=True)
    usuario: Mapped["Usuario"] = relationship("Usuario", back_populates="fuentes")

    def __repr__(self):
        return f"<Fuente {self.nombre} - {self.url_listado}>"


# --- MODELO DE NOTICIAS ---
class Noticia(Base):
    __tablename__ = "noticias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(1000), unique=True, index=True)
    fuente: Mapped[str] = mapped_column(String(200), index=True)
    titulo: Mapped[str] = mapped_column(String(1000))
    contenido: Mapped[str] = mapped_column(Text)
    fecha_publicacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    imagen_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    categoria: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    cambios: Mapped[list["CambioNoticia"]] = relationship(
        back_populates="noticia", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_noticias_fuente_fecha", "fuente", "fecha_publicacion"),
    )

    def __repr__(self):
        return f"<Noticia {self.id} - {self.titulo[:50]}...>"


# --- MODELO DE CAMBIOS EN NOTICIAS ---
class CambioNoticia(Base):
    __tablename__ = "cambios_noticia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    noticia_id: Mapped[int] = mapped_column(ForeignKey("noticias.id"), index=True)
    campo: Mapped[str] = mapped_column(String(50))  # 'titulo' | 'contenido'
    valor_anterior: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor_nuevo: Mapped[str | None] = mapped_column(Text, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    noticia: Mapped["Noticia"] = relationship(back_populates="cambios")

    def __repr__(self):
        return f"<CambioNoticia {self.id} - {self.campo}>"


# --- MODELO DE POSTS DE REDES SOCIALES ---
class SocialMediaPost(Base):
    __tablename__ = "social_media_posts"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(50))  # 'twitter', 'facebook'
    username: Mapped[str] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    likes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shares: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retweets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    post_created_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(100))  # 'rpp', 'elcomercio', etc.
    
    # Relación con usuario (opcional, si quieres asociar posts a usuarios)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey('usuarios.id'), nullable=True)
    
    __table_args__ = (
        Index("ix_social_platform_source", "platform", "source"),
        Index("ix_social_created_at", "created_at"),
    )

    def __repr__(self):
        return f"<SocialMediaPost {self.id} - {self.platform}:{self.username}>"


# --- MODELO DE BENEFICIOS DE PLANES ---
class PlanBeneficio(Base):
    __tablename__ = "plan_beneficios"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    plan: Mapped[str] = mapped_column(String(50), nullable=False)  # 'gratis', 'premium', 'ambos'
    categoria: Mapped[str] = mapped_column(String(100), nullable=False)  # 'noticias', 'exportacion', 'soporte'
    caracteristica: Mapped[str] = mapped_column(String(200), nullable=False)
    valor_gratis: Mapped[str | None] = mapped_column(String(100), nullable=True)
    valor_premium: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ilimitado_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    es_exclusivo: Mapped[bool] = mapped_column(Boolean, default=False)  # Solo para premium
    orden: Mapped[int] = mapped_column(Integer, default=0)
    
    def __repr__(self):
        return f"<PlanBeneficio {self.plan} - {self.caracteristica}>"


# --- MODELO DE MOVIMIENTOS / AUDITORÍA ---
class Movimiento(Base):
    __tablename__ = "movimientos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey('usuarios.id'), nullable=True, index=True)
    accion: Mapped[str] = mapped_column(String(100))  # 'remind_trials' | 'upgrade_plan' | 'export' | etc.
    detalle: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def __repr__(self):
        return f"<Movimiento {self.id} - {self.accion}>"