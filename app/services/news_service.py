# app/services/news_service.py
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from app.models import Noticia, CambioNoticia
from app.services.scraper_service import map_to_allowed_category


def upsert_noticia(db: Session, data: dict) -> Noticia:
    """
    Inserta o actualiza una noticia en la base de datos.
    Si la noticia ya existe (por URL), actualiza los campos modificados y registra los cambios.
    """

    # Validar datos mínimos requeridos
    required_fields = ["url", "fuente", "titulo", "contenido"]
    for field in required_fields:
        if not data.get(field):
            raise ValueError(f"El campo '{field}' es obligatorio para guardar una noticia.")

    try:
        # Buscar noticia existente por URL
        noticia = db.query(Noticia).filter_by(url=data["url"]).first()

        if not noticia:
            # --- Nueva noticia ---
            # Asegurar que la categoría nueva esté dentro de las permitidas
            cat = map_to_allowed_category(data.get("categoria"))

            noticia = Noticia(
                url=data["url"],
                fuente=data["fuente"],
                titulo=data["titulo"],
                contenido=data["contenido"],
                fecha_publicacion=data.get("fecha_publicacion"),
                imagen_path=data.get("imagen_path"),
                categoria=cat,
            )
            db.add(noticia)
            db.commit()
            db.refresh(noticia)
            return noticia

        # --- Noticia existente: verificar cambios ---
        cambios = []

        campos_actualizables = ["titulo", "contenido", "imagen_path", "fecha_publicacion", "categoria"]

        for campo in campos_actualizables:
            nuevo_valor = data.get(campo)
            if campo == 'categoria':
                nuevo_valor = map_to_allowed_category(nuevo_valor)
            valor_actual = getattr(noticia, campo)

            if nuevo_valor and nuevo_valor != valor_actual:
                cambios.append((campo, valor_actual, nuevo_valor))
                setattr(noticia, campo, nuevo_valor)

        # Registrar los cambios en tabla de auditoría
        for campo, antes, nuevo in cambios:
            cambio = CambioNoticia(
                noticia_id=noticia.id,
                campo=campo,
                valor_anterior=antes,
                valor_nuevo=nuevo,
                detected_at=datetime.utcnow()
            )
            db.add(cambio)

        # Actualizar timestamp
        noticia.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(noticia)

        return noticia

    except SQLAlchemyError as e:
        db.rollback()
        print(f"[❌ ERROR] Error SQL al insertar/actualizar noticia: {e}")
        raise
    except Exception as e:
        db.rollback()
        print(f"[❌ ERROR] Error general en upsert_noticia: {e}")
        raise
