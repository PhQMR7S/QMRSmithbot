from fastapi.testclient import TestClient

from qmrsmithbot.api.app import app


def test_dashboard_and_assets_have_safe_headers():
    with TestClient(app) as client:
        for path in ['/dashboard', '/dashboard/callback', '/dashboard/assets/app.js',
                     '/dashboard/assets/style.css', '/dashboard/assets/api.js',
                     '/dashboard/assets/i18n.js']:
            response = client.get(path)
            assert response.status_code == 200
            assert response.headers['cache-control'] == 'no-store'
            assert "frame-ancestors 'none'" in response.headers['content-security-policy']
            assert response.headers['referrer-policy'] == 'no-referrer'
        assert client.get('/dashboard/assets/config.py').status_code == 404
        assert client.get('/api/v1/projects').status_code == 401
