from fastapi import APIRouter
from app.database import health_check_db

router = APIRouter()

@router.get("/health")
def health():
    health_check_db()
    return {"status": "ok"}
