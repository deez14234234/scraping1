from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from app.ml.modelo import entrenar_y_evaluar

router = APIRouter(prefix="/web", tags=["Métricas"])

# --- Página principal de métricas ---
@router.get("/metrics", response_class=HTMLResponse)
async def metrics_page(request: Request):
    """
    Muestra las métricas de desempeño del modelo ML
    """
    try:
        resultados = entrenar_y_evaluar()
    except Exception as e:
        resultados = {
            "precision": 0,
            "recall": 0,
            "f1": 0,
            "auc": None,
            "image": "/static/images/error.png"
        }
        print(f"⚠️ Error al generar métricas: {e}")

    return templates.TemplateResponse("metrics.html", {
        "request": request,
        "resultados": resultados
    })


# --- Endpoint para reentrenar el modelo ---
@router.post("/metrics/train")
async def retrain_model(request: Request):
    """
    Permite reentrenar el modelo desde la interfaz web.
    """
    try:
        resultados = entrenar_y_evaluar()
        print("✅ Modelo reentrenado correctamente.")
        return templates.TemplateResponse("metrics.html", {
            "request": request,
            "resultados": resultados,
            "msg": "Modelo reentrenado con éxito ✅"
        })
    except Exception as e:
        print(f"❌ Error al reentrenar el modelo: {e}")
        return templates.TemplateResponse("metrics.html", {
            "request": request,
            "resultados": {
                "precision": 0,
                "recall": 0,
                "f1": 0,
                "auc": None,
                "image": "/static/images/error.png"
            },
            "msg": f"Error: {e}"
        })
