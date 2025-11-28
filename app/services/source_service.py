# app/services/source_service.py
from datetime import datetime
from sqlalchemy.orm import Session
from app.models import Fuente, Usuario
from urllib.parse import urlparse

def add_fuente(db: Session, url_listado: str, nombre: str | None = None, usuario_id: int | None = None) -> Fuente:
    """Agrega una nueva fuente con verificación de límites por usuario."""
    url_listado = url_listado.strip()
    
    # Verificar si ya existe la fuente para este usuario
    obj = db.query(Fuente).filter_by(url_listado=url_listado, usuario_id=usuario_id).first()
    if obj:
        # Ya existe para este usuario, actualiza nombre si llega
        if nombre and not obj.nombre:
            obj.nombre = nombre
            db.commit()
        return obj
    
    # Verificar límites si es un usuario específico
    if usuario_id:
        usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
        if usuario:
            if usuario.plan == "gratis":
                # Contar fuentes actuales del usuario
                fuentes_count = db.query(Fuente).filter(
                    Fuente.usuario_id == usuario_id,
                    Fuente.habilitada == True
                ).count()
                
                max_fuentes = usuario.max_fuentes or 3
                if fuentes_count >= max_fuentes:
                    raise ValueError(
                        f"Límite alcanzado: Plan Gratis permite máximo {max_fuentes} fuentes. "
                        f"Tienes {fuentes_count} fuentes. Actualiza a Premium para más."
                    )
    
    # Crear nueva fuente
    if not nombre:
        nombre = urlparse(url_listado).netloc
    
    obj = Fuente(
        url_listado=url_listado, 
        nombre=nombre, 
        habilitada=True,
        usuario_id=usuario_id  # Asignar usuario si existe
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj

def mark_scraped(db: Session, fuente_id: int):
    """Marca una fuente como scrapeada actualizando su timestamp."""
    f = db.get(Fuente, fuente_id)
    if f:
        f.last_scraped_at = datetime.utcnow()
        db.commit()

def get_fuentes_por_usuario(db: Session, usuario_id: int, solo_habilitadas: bool = True):
    """Obtiene las fuentes de un usuario específico."""
    query = db.query(Fuente).filter(Fuente.usuario_id == usuario_id)
    
    if solo_habilitadas:
        query = query.filter(Fuente.habilitada == True)
    
    return query.all()

def contar_fuentes_usuario(db: Session, usuario_id: int) -> int:
    """Cuenta las fuentes habilitadas de un usuario."""
    return db.query(Fuente).filter(
        Fuente.usuario_id == usuario_id,
        Fuente.habilitada == True
    ).count()

def puede_agregar_fuente(db: Session, usuario_id: int) -> tuple[bool, str]:
    """Verifica si un usuario puede agregar más fuentes según su plan."""
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        return False, "Usuario no encontrado"
    
    if usuario.plan == "premium":
        return True, "Puedes agregar fuentes ilimitadas"
    
    # Para usuarios gratis, verificar límite
    cantidad_actual = contar_fuentes_usuario(db, usuario_id)
    max_fuentes = usuario.max_fuentes or 3
    
    if cantidad_actual < max_fuentes:
        return True, f"Puedes agregar {max_fuentes - cantidad_actual} fuente(s) más"
    else:
        return False, f"Límite alcanzado: Máximo {max_fuentes} fuentes en plan Gratis"

def obtener_fuentes_permitidas(db: Session, usuario_id: int):
    """Obtiene las fuentes que un usuario puede scrapear según su plan."""
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        return []
    
    query = db.query(Fuente).filter(
        Fuente.usuario_id == usuario_id,
        Fuente.habilitada == True
    )
    
    # Para usuarios gratis, limitar a las primeras X fuentes
    if usuario.plan == "gratis":
        max_fuentes = usuario.max_fuentes or 3
        query = query.order_by(Fuente.id).limit(max_fuentes)
    
    return query.all()

def verificar_permiso_fuente(db: Session, usuario_id: int, fuente_id: int) -> bool:
    """Verifica si un usuario tiene permiso para usar una fuente específica."""
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id).first()
    if not usuario:
        return False
    
    # Usuarios premium pueden acceder a todas sus fuentes
    if usuario.plan == "premium":
        fuente = db.query(Fuente).filter(
            Fuente.id == fuente_id,
            Fuente.usuario_id == usuario_id
        ).first()
        return fuente is not None
    
    # Para usuarios gratis: solo las primeras X fuentes
    max_fuentes = usuario.max_fuentes or 3
    fuentes_permitidas = db.query(Fuente).filter(
        Fuente.usuario_id == usuario_id,
        Fuente.habilitada == True
    ).order_by(Fuente.id).limit(max_fuentes).all()
    
    return any(fuente.id == fuente_id for fuente in fuentes_permitidas)

def habilitar_fuente(db: Session, fuente_id: int, usuario_id: int) -> bool:
    """Habilita una fuente si el usuario tiene permiso."""
    if not verificar_permiso_fuente(db, usuario_id, fuente_id):
        return False
    
    fuente = db.query(Fuente).filter(Fuente.id == fuente_id).first()
    if fuente:
        fuente.habilitada = True
        db.commit()
        return True
    return False

def deshabilitar_fuente(db: Session, fuente_id: int, usuario_id: int) -> bool:
    """Deshabilita una fuente si pertenece al usuario."""
    fuente = db.query(Fuente).filter(
        Fuente.id == fuente_id,
        Fuente.usuario_id == usuario_id
    ).first()
    
    if fuente:
        fuente.habilitada = False
        db.commit()
        return True
    return False

def eliminar_fuente(db: Session, fuente_id: int, usuario_id: int) -> bool:
    """Elimina una fuente si pertenece al usuario."""
    fuente = db.query(Fuente).filter(
        Fuente.id == fuente_id,
        Fuente.usuario_id == usuario_id
    ).first()
    
    if fuente:
        db.delete(fuente)
        db.commit()
        return True
    return False