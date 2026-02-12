from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from config import Settings


def build_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.get_cors_origins(),
        allow_credentials=settings.cors_allow_credentials(),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    return app


def test_preflight_allows_explicit_origin_with_credentials() -> None:
    settings = Settings(CORS_ORIGINS="https://app.example.com,https://admin.example.com")
    app = build_app(settings)

    with TestClient(app) as client:
        response = client.options(
            "/ping",
            headers={
                "Origin": "https://app.example.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.example.com"
    assert response.headers["access-control-allow-credentials"] == "true"
    assert "authorization" in response.headers["access-control-allow-headers"].lower()


def test_wildcard_cannot_be_mixed_with_explicit_origins() -> None:
    settings = Settings(CORS_ORIGINS="*,https://app.example.com")

    try:
        settings.get_cors_origins()
        assert False, "Expected ValueError when mixing wildcard and explicit origins"
    except ValueError as exc:
        assert "cannot mix '*' with explicit origins" in str(exc)
