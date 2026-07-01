from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import configure_cors


def _build_app(allowed_origins: list[str]) -> TestClient:
    app = FastAPI()
    configure_cors(app, allowed_origins)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return TestClient(app)


def test_allowed_origin_gets_cors_header():
    client = _build_app(["https://example.github.io"])
    response = client.get("/health", headers={"Origin": "https://example.github.io"})
    assert response.headers.get("access-control-allow-origin") == "https://example.github.io"


def test_unlisted_origin_does_not_get_cors_header():
    client = _build_app(["https://example.github.io"])
    response = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_no_configured_origins_means_no_cors_header():
    client = _build_app([])
    response = client.get("/health", headers={"Origin": "https://example.github.io"})
    assert "access-control-allow-origin" not in response.headers
