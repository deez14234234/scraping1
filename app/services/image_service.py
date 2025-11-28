import os, pathlib, requests
from app.config import settings

IMAGES_DIR = pathlib.Path("data/images")
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

def download_image(url: str) -> str | None:
    try:
        resp = requests.get(url, headers={"User-Agent": settings.USER_AGENT}, timeout=settings.REQUEST_TIMEOUT)
        resp.raise_for_status()
        ext = ".jpg"
        filename = IMAGES_DIR / (os.urandom(8).hex() + ext)
        with open(filename, "wb") as f:
            f.write(resp.content)
        return str(filename)
    except Exception:
        return None
