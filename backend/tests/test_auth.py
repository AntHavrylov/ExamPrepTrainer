from app.models import RefreshToken, User


def test_register_returns_201(client):
    response = client.post("/auth/register", json={"email": "user@example.com", "password": "supersecret"})
    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "user@example.com"
    assert "password" not in body
    assert "hashed_password" not in body


def test_register_defaults_language_to_english(client):
    response = client.post("/auth/register", json={"email": "lang-default@example.com", "password": "supersecret"})
    assert response.json()["language"] == "en"


def test_register_accepts_explicit_language(client):
    response = client.post(
        "/auth/register",
        json={"email": "lang-uk@example.com", "password": "supersecret", "language": "uk"},
    )
    assert response.status_code == 201
    assert response.json()["language"] == "uk"


def test_register_rejects_unsupported_language(client):
    response = client.post(
        "/auth/register",
        json={"email": "lang-bad@example.com", "password": "supersecret", "language": "fr"},
    )
    assert response.status_code == 422


def test_register_duplicate_email_returns_409(client):
    client.post("/auth/register", json={"email": "dup@example.com", "password": "supersecret"})
    response = client.post("/auth/register", json={"email": "dup@example.com", "password": "other-pass"})
    assert response.status_code == 409


def test_two_distinct_users_can_register_and_login(client):
    client.post("/auth/register", json={"email": "u1@example.com", "password": "passpass1"})
    client.post("/auth/register", json={"email": "u2@example.com", "password": "passpass2"})

    login1 = client.post("/auth/login", json={"email": "u1@example.com", "password": "passpass1"})
    login2 = client.post("/auth/login", json={"email": "u2@example.com", "password": "passpass2"})

    assert login1.status_code == 200
    assert login2.status_code == 200
    assert login1.json()["access_token"] != login2.json()["access_token"]
    assert login1.json()["refresh_token"] != login2.json()["refresh_token"]


def test_login_with_wrong_password_returns_401(client):
    client.post("/auth/register", json={"email": "wrong@example.com", "password": "supersecret"})
    response = client.post("/auth/login", json={"email": "wrong@example.com", "password": "nope"})
    assert response.status_code == 401


def test_login_with_unknown_email_returns_401(client):
    response = client.post("/auth/login", json={"email": "ghost@example.com", "password": "whatever"})
    assert response.status_code == 401


def test_me_without_token_returns_401(client):
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_with_invalid_token_returns_401(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_me_with_valid_token_returns_user(client):
    client.post("/auth/register", json={"email": "me@example.com", "password": "supersecret"})
    login = client.post("/auth/login", json={"email": "me@example.com", "password": "supersecret"})
    token = login.json()["access_token"]

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == "me@example.com"


def test_password_is_stored_only_as_hash(client, db_session):
    raw_password = "supersecret"
    client.post("/auth/register", json={"email": "hash@example.com", "password": raw_password})

    user = db_session.query(User).filter_by(email="hash@example.com").one()
    assert user.hashed_password != raw_password
    assert raw_password not in user.hashed_password
    assert user.hashed_password.startswith("$2b$")


def test_refresh_token_is_stored_only_as_hash(client, db_session):
    client.post("/auth/register", json={"email": "rt-hash@example.com", "password": "supersecret"})
    login = client.post("/auth/login", json={"email": "rt-hash@example.com", "password": "supersecret"})
    raw_refresh_token = login.json()["refresh_token"]

    stored = db_session.query(RefreshToken).one()
    assert stored.token_hash != raw_refresh_token
    assert raw_refresh_token not in stored.token_hash


def test_refresh_issues_new_tokens_and_rotates_old_one(client):
    client.post("/auth/register", json={"email": "refresh@example.com", "password": "supersecret"})
    login = client.post("/auth/login", json={"email": "refresh@example.com", "password": "supersecret"})
    old_refresh_token = login.json()["refresh_token"]

    refreshed = client.post("/auth/refresh", json={"refresh_token": old_refresh_token})
    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != old_refresh_token

    new_access_token = refreshed.json()["access_token"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {new_access_token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "refresh@example.com"

    reused = client.post("/auth/refresh", json={"refresh_token": old_refresh_token})
    assert reused.status_code == 401


def test_refresh_with_unknown_token_returns_401(client):
    response = client.post("/auth/refresh", json={"refresh_token": "not-a-real-refresh-token"})
    assert response.status_code == 401


def test_logout_revokes_refresh_token(client):
    client.post("/auth/register", json={"email": "logout@example.com", "password": "supersecret"})
    login = client.post("/auth/login", json={"email": "logout@example.com", "password": "supersecret"})
    refresh_token = login.json()["refresh_token"]

    logout = client.post("/auth/logout", json={"refresh_token": refresh_token})
    assert logout.status_code == 204

    reused = client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert reused.status_code == 401
