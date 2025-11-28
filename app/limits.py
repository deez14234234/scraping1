from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.models import Usuario, Fuente

class LimitManager:
    def __init__(self, db: Session, usuario: Usuario):
        self.db = db
        self.usuario = usuario
    
    def puede_agregar_fuente(self):
        """Verifica si el usuario puede agregar una nueva fuente"""
        if self.usuario.plan == "premium":
            return True
        
        # Contar fuentes actuales del usuario
        count = self.db.query(Fuente).filter(
            Fuente.usuario_id == self.usuario.id,
            Fuente.habilitada == True
        ).count()
        
        return count < self.usuario.max_fuentes
    
    def puede_scrapear_fuente(self, fuente_id: int):
        """Verifica si el usuario puede scrapear una fuente"""
        if self.usuario.plan == "premium":
            return True
        
        # Obtener fuentes del usuario (ordenadas por ID o fecha)
        fuentes_usuario = self.db.query(Fuente).filter(
            Fuente.usuario_id == self.usuario.id,
            Fuente.habilitada == True
        ).order_by(Fuente.id).limit(self.usuario.max_fuentes).all()
        
        # Verificar si la fuente está entre las permitidas
        fuente_permitida = any(fuente.id == fuente_id for fuente in fuentes_usuario)
        
        if not fuente_permitida:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Plan Gratis limitado a {self.usuario.max_fuentes} fuentes. Actualiza a Premium para más."
            )
        
        return True
    
    def puede_exportar(self):
        """Verifica límites de exportación"""
        # Implementar lógica de límites de exportación
        pass
    
    def puede_usar_analisis_sentimiento(self):
        """Verifica si puede usar análisis de sentimiento"""
        if self.usuario.plan == "premium":
            return True
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Análisis de sentimiento exclusivo para plan Premium"
        )

# Dependencia para FastAPI
def get_limit_manager(
    current_user: Usuario = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    return LimitManager(db, current_user)