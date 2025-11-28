# app/scripts/load_benefits.py
from app.database import SessionLocal
from app.models import PlanBeneficio

def cargar_beneficios_planes():
    db = SessionLocal()
    
    beneficios = [
        # NOTICIAS
        {"plan": "ambos", "categoria": "noticias", "caracteristica": "Límite mensual de noticias", 
         "valor_gratis": "100", "valor_premium": "Ilimitadas", "ilimitado_premium": True, "orden": 1},
        
        {"plan": "ambos", "categoria": "noticias", "caracteristica": "Fuentes de noticias", 
         "valor_gratis": "5", "valor_premium": "50", "ilimitado_premium": False, "orden": 2},
        
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
        
        {"plan": "premium", "categoria": "api", "caracteristica": "API requests/día", 
         "valor_gratis": "100", "valor_premium": "10,000", "ilimitado_premium": False, "es_exclusivo": False, "orden": 12},
        
        {"plan": "premium", "categoria": "api", "caracteristica": "Webhooks", 
         "valor_gratis": "❌ No", "valor_premium": "✅ Sí", "ilimitado_premium": False, "es_exclusivo": True, "orden": 13},
        
        {"plan": "premium", "categoria": "reportes", "caracteristica": "Reportes automáticos", 
         "valor_gretis": "❌ No", "valor_premium": "✅ Sí", "ilimitado_premium": False, "es_exclusivo": True, "orden": 14},
        
        # SOPORTE
        {"plan": "ambos", "categoria": "soporte", "caracteristica": "Soporte", 
         "valor_gratis": "Documentación", "valor_premium": "24/7 Prioritario", "ilimitado_premium": False, "orden": 15},
        
        {"plan": "ambos", "categoria": "soporte", "caracteristica": "SLA disponibilidad", 
         "valor_gratis": "Mejor esfuerzo", "valor_premium": "99.9%", "ilimitado_premium": False, "orden": 16},
    ]
    
    try:
        # Limpiar beneficios existentes
        db.query(PlanBeneficio).delete()
        
        # Insertar nuevos beneficios
        for beneficio in beneficios:
            nuevo_beneficio = PlanBeneficio(**beneficio)
            db.add(nuevo_beneficio)
        
        db.commit()
        print("✅ Beneficios de planes cargados exitosamente")
        print(f"📊 Total: {len(beneficios)} beneficios configurados")
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error cargando beneficios: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    cargar_beneficios_planes()