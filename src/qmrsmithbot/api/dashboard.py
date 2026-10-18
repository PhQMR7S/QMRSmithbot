"""Same-origin dashboard with a strict script/content policy."""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(include_in_schema=False)
ROOT = Path(__file__).resolve().parents[1] / 'dashboard'
HEADERS = {
    'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; "
    "connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; "
    "frame-ancestors 'none'; form-action 'self'",
    'Referrer-Policy': 'no-referrer',
    'X-Content-Type-Options': 'nosniff',
    'Cache-Control': 'no-store',
}


@router.get('/dashboard')
@router.get('/dashboard/callback')
async def dashboard():
    return FileResponse(ROOT / 'index.html', headers=HEADERS)


@router.get('/dashboard/assets/{filename}')
async def dashboard_asset(filename: str):
    if filename not in {'app.js', 'api.js', 'i18n.js', 'style.css', 'studio.js', 'forms.js'}:
        raise HTTPException(status_code=404)
    return FileResponse(ROOT / filename, headers=HEADERS)
