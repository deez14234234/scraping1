from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/web", tags=["web"])
templates = Jinja2Templates(directory="app/web/templates")


@router.get("/payments", response_class=HTMLResponse)
def payments_page(request: Request):
    """Página simple de Pagos con dos cards (Normal y Premium)."""
    return templates.TemplateResponse(
        "payments.html",
        {"request": request},
    )
