import importlib
import sys
from pathlib import Path

from fastapi.testclient import TestClient

SRC_DIR = Path(__file__).resolve().parents[1]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from api.main import app
from core.config import CORS_ALLOWED_ORIGINS


def _reload_runtime_modules():
    import core.config as config_module
    import api.main as main_module

    importlib.reload(config_module)
    return importlib.reload(main_module)


def _restore_runtime_modules():
    import core.config as config_module
    import api.main as main_module

    importlib.reload(config_module)
    importlib.reload(main_module)


def _login_and_cookie_header(client: TestClient) -> str:
    from services.admin_service import reset_admin_state

    reset_admin_state()
    response = client.post(
        "/auth/login",
        json={"email": "admin@demo.local", "password": "demo1234", "tenant_id": "default"},
    )
    assert response.status_code == 200, response.text
    cookie = response.headers.get("set-cookie")
    assert cookie
    return cookie.lower()


def test_cors_preflight_allows_configured_origin():
    client = TestClient(app)
    origin = CORS_ALLOWED_ORIGINS[0]

    response = client.options(
        "/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin


def test_cors_preflight_allows_playwright_smoke_origin():
    client = TestClient(app)
    origin = "http://127.0.0.1:3015"

    assert origin in CORS_ALLOWED_ORIGINS

    response = client.options(
        "/auth/login",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == origin


def test_cors_preflight_rejects_unknown_origin():
    client = TestClient(app)

    response = client.options(
        "/health",
        headers={
            "Origin": "http://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 400
    assert response.headers.get("access-control-allow-origin") is None


def test_cors_preflight_respects_environment_allowlist(monkeypatch):
    try:
        with monkeypatch.context() as scoped:
            scoped.setenv("CORS_ALLOWED_ORIGINS", "https://console.example.com")
            scoped.setenv("CORS_ALLOW_CREDENTIALS", "true")
            main_module = _reload_runtime_modules()
            client = TestClient(main_module.app)

            allowed = client.options(
                "/auth/login",
                headers={
                    "Origin": "https://console.example.com",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            denied = client.options(
                "/auth/login",
                headers={
                    "Origin": "https://evil.example.com",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )

            assert allowed.status_code == 200
            assert allowed.headers.get("access-control-allow-origin") == "https://console.example.com"
            assert denied.status_code == 400
            assert denied.headers.get("access-control-allow-origin") is None
    finally:
        _restore_runtime_modules()


def test_cors_wildcard_is_not_allowed_when_credentials_are_enabled(monkeypatch):
    try:
        with monkeypatch.context() as scoped:
            scoped.setenv("CORS_ALLOWED_ORIGINS", "*,https://console.example.com")
            scoped.setenv("CORS_ALLOW_CREDENTIALS", "true")
            main_module = _reload_runtime_modules()
            client = TestClient(main_module.app)

            assert "*" not in main_module.allowed_cors_origins

            allowed = client.options(
                "/health",
                headers={
                    "Origin": "https://console.example.com",
                    "Access-Control-Request-Method": "GET",
                },
            )
            denied = client.options(
                "/health",
                headers={
                    "Origin": "https://evil.example.com",
                    "Access-Control-Request-Method": "GET",
                },
            )

            assert allowed.status_code == 200
            assert allowed.headers.get("access-control-allow-origin") == "https://console.example.com"
            assert denied.status_code == 400
            assert denied.headers.get("access-control-allow-origin") is None
    finally:
        _restore_runtime_modules()


def test_session_cookie_is_secure_httponly_and_samesite_by_default(monkeypatch):
    try:
        with monkeypatch.context() as scoped:
            scoped.delenv("SESSION_COOKIE_SECURE", raising=False)
            scoped.delenv("SESSION_COOKIE_SAMESITE", raising=False)
            main_module = _reload_runtime_modules()
            cookie = _login_and_cookie_header(TestClient(main_module.app))

            assert "httponly" in cookie
            assert "secure" in cookie
            assert "samesite=lax" in cookie
    finally:
        _restore_runtime_modules()


def test_session_cookie_can_disable_secure_for_local_http_without_dropping_guards(monkeypatch):
    try:
        with monkeypatch.context() as scoped:
            scoped.setenv("SESSION_COOKIE_SECURE", "false")
            scoped.delenv("SESSION_COOKIE_SAMESITE", raising=False)
            main_module = _reload_runtime_modules()
            cookie = _login_and_cookie_header(TestClient(main_module.app))

            assert "httponly" in cookie
            assert "; secure" not in cookie
            assert "samesite=lax" in cookie
    finally:
        _restore_runtime_modules()
