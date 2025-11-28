# app/routes/plans.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import PlanBeneficio
from typing import Dict, List

router = APIRouter()

@router.get("/api/plans/benefits")
async def get_plan_benefits(db: Session = Depends(get_db)):
    """Obtiene todos los beneficios organizados por categoría"""
    beneficios = db.query(PlanBeneficio).order_by(PlanBeneficio.orden).all()
    
    categorias = {}
    for beneficio in beneficios:
        if beneficio.categoria not in categorias:
            categorias[beneficio.categoria] = []
        
        categorias[beneficio.categoria].append({
            "id": beneficio.id,
            "caracteristica": beneficio.caracteristica,
            "valor_gratis": beneficio.valor_gratis,
            "valor_premium": beneficio.valor_premium,
            "ilimitado_premium": beneficio.ilimitado_premium,
            "es_exclusivo": beneficio.es_exclusivo,
            "plan": beneficio.plan
        })
    
    return {
        "categorias": categorias,
        "total_beneficios": len(beneficios)
    }

@router.get("/web/plans")
async def plans_page():
    """Página de planes y precios"""
    # Esta ruta renderizará el template con los planes
    return {"message": "Página de planes"}