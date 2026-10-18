import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

from qmrsmithbot.api.app import app


def test_vercel_entrypoint_exports_existing_application():
    path = Path(__file__).resolve().parents[1] / 'app.py'
    spec = importlib.util.spec_from_file_location('vercel_entrypoint', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.app is app
    with TestClient(module.app) as client:
        assert client.get('/health').json()['status'] == 'ok'
        assert client.get('/api/v1/languages').status_code == 200
