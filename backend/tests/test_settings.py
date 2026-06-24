from sqlalchemy import select

import app.routers.settings as settings_router
from app.ai.client import get_ai_provider_factory, get_default_ai_provider
from app.main import app
from app.models import UserApiKey


class _StubProvider:
    def __init__(self, valid: bool = True, models=None):
        self.valid = valid
        self.models = models or [{"id": "m/1", "name": "Model One", "context_length": 4096}]

    async def validate_key(self) -> bool:
        return self.valid

    async def list_models(self):
        return self.models


def _stub_factory(valid: bool):
    def factory(api_key: str, model: str):
        return _StubProvider(valid=valid)

    return factory


def setup_function():
    settings_router._models_cache = None


def teardown_function():
    app.dependency_overrides.pop(get_ai_provider_factory, None)
    app.dependency_overrides.pop(get_default_ai_provider, None)
    settings_router._models_cache = None


def test_api_key_status_requires_auth(client):
    response = client.get("/settings/api-key")
    assert response.status_code == 401


def test_api_key_status_defaults_to_no_key(client, make_user):
    headers = make_user("settings-default@example.com")
    response = client.get("/settings/api-key", headers=headers)
    assert response.status_code == 200
    assert response.json() == {"has_key": False, "model": None}


def test_save_api_key_rejects_invalid_key(client, make_user, db_session):
    headers = make_user("settings-invalid@example.com")
    app.dependency_overrides[get_ai_provider_factory] = lambda: _stub_factory(valid=False)

    response = client.put(
        "/settings/api-key", json={"api_key": "bad-key", "model": "m/1"}, headers=headers
    )

    assert response.status_code == 422
    assert "could not be verified" in response.json()["detail"]
    assert db_session.scalar(select(UserApiKey)) is None


def test_save_api_key_persists_encrypted_and_returns_status(client, make_user, db_session):
    headers = make_user("settings-valid@example.com")
    app.dependency_overrides[get_ai_provider_factory] = lambda: _stub_factory(valid=True)

    response = client.put(
        "/settings/api-key", json={"api_key": "sk-or-secret-123", "model": "openai/gpt-4o"}, headers=headers
    )

    assert response.status_code == 200
    assert response.json() == {"has_key": True, "model": "openai/gpt-4o"}

    row = db_session.scalar(select(UserApiKey))
    assert row is not None
    assert row.model == "openai/gpt-4o"
    assert row.encrypted_api_key != "sk-or-secret-123"
    assert "sk-or-secret-123" not in response.text

    status_response = client.get("/settings/api-key", headers=headers)
    assert status_response.json() == {"has_key": True, "model": "openai/gpt-4o"}


def test_save_api_key_overwrites_existing(client, make_user, db_session):
    headers = make_user("settings-overwrite@example.com")
    app.dependency_overrides[get_ai_provider_factory] = lambda: _stub_factory(valid=True)

    client.put("/settings/api-key", json={"api_key": "key-one", "model": "model/a"}, headers=headers)
    client.put("/settings/api-key", json={"api_key": "key-two", "model": "model/b"}, headers=headers)

    rows = list(db_session.scalars(select(UserApiKey)))
    assert len(rows) == 1
    assert rows[0].model == "model/b"


def test_remove_api_key_deletes_row_and_clears_model(client, make_user, db_session):
    headers = make_user("settings-remove@example.com")
    app.dependency_overrides[get_ai_provider_factory] = lambda: _stub_factory(valid=True)
    client.put("/settings/api-key", json={"api_key": "key-one", "model": "model/a"}, headers=headers)

    response = client.delete("/settings/api-key", headers=headers)
    assert response.status_code == 204

    assert db_session.scalar(select(UserApiKey)) is None
    status_response = client.get("/settings/api-key", headers=headers)
    assert status_response.json() == {"has_key": False, "model": None}


def test_remove_api_key_when_none_configured_is_a_no_op(client, make_user):
    headers = make_user("settings-remove-noop@example.com")
    response = client.delete("/settings/api-key", headers=headers)
    assert response.status_code == 204


def test_list_models_requires_auth(client):
    response = client.get("/settings/models")
    assert response.status_code == 401


def test_list_models_returns_provider_catalog(client, make_user):
    headers = make_user("settings-models@example.com")
    stub = _StubProvider(models=[{"id": "a/1", "name": "A", "context_length": 1000}])
    app.dependency_overrides[get_default_ai_provider] = lambda: stub

    response = client.get("/settings/models", headers=headers)

    assert response.status_code == 200
    assert response.json() == [{"id": "a/1", "name": "A", "context_length": 1000}]


def test_list_models_is_cached_across_requests(client, make_user):
    headers = make_user("settings-models-cache@example.com")
    stub = _StubProvider(models=[{"id": "a/1", "name": "A", "context_length": None}])
    calls = {"n": 0}

    async def counting_list_models():
        calls["n"] += 1
        return stub.models

    stub.list_models = counting_list_models
    app.dependency_overrides[get_default_ai_provider] = lambda: stub

    client.get("/settings/models", headers=headers)
    client.get("/settings/models", headers=headers)

    assert calls["n"] == 1


def test_update_language_requires_auth(client):
    response = client.put("/settings/language", json={"language": "uk"})
    assert response.status_code == 401


def test_update_language_persists_and_is_reflected_in_me(client, make_user):
    headers = make_user("settings-language@example.com")

    response = client.put("/settings/language", json={"language": "uk"}, headers=headers)
    assert response.status_code == 200
    assert response.json()["language"] == "uk"

    me = client.get("/auth/me", headers=headers)
    assert me.json()["language"] == "uk"


def test_update_language_rejects_unsupported_language(client, make_user):
    headers = make_user("settings-language-invalid@example.com")
    response = client.put("/settings/language", json={"language": "fr"}, headers=headers)
    assert response.status_code == 422
