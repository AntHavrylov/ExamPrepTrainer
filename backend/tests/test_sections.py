from app.config import settings


def test_user_can_create_add_edit_delete_document(client, make_user):
    headers = make_user("a@example.com")

    section = client.post("/sections", json={"name": "Python", "description": "Core language"}, headers=headers)
    assert section.status_code == 201
    section_id = section.json()["id"]

    doc = client.post(
        f"/sections/{section_id}/documents",
        json={"title": "Notes", "content": "Initial notes"},
        headers=headers,
    )
    assert doc.status_code == 201
    document_id = doc.json()["id"]
    assert doc.json()["content"] == "Initial notes"

    fetched = client.get(f"/sections/{section_id}", headers=headers)
    assert fetched.status_code == 200
    assert len(fetched.json()["documents"]) == 1

    edited = client.put(
        f"/documents/{document_id}",
        json={"title": "Notes", "content": "Updated notes"},
        headers=headers,
    )
    assert edited.status_code == 200
    assert edited.json()["content"] == "Updated notes"

    deleted = client.delete(f"/documents/{document_id}", headers=headers)
    assert deleted.status_code == 204

    fetched_after = client.get(f"/sections/{section_id}", headers=headers)
    assert fetched_after.json()["documents"] == []


def test_user_b_sees_empty_section_list(client, make_user):
    headers_a = make_user("a2@example.com")
    headers_b = make_user("b2@example.com")

    client.post("/sections", json={"name": "Secret"}, headers=headers_a)

    list_b = client.get("/sections", headers=headers_b)
    assert list_b.status_code == 200
    assert list_b.json() == []


def test_user_b_cannot_view_user_a_section(client, make_user):
    headers_a = make_user("a3@example.com")
    headers_b = make_user("b3@example.com")

    section = client.post("/sections", json={"name": "Secret"}, headers=headers_a).json()

    response = client.get(f"/sections/{section['id']}", headers=headers_b)
    assert response.status_code in (403, 404)


def test_user_b_cannot_edit_user_a_document(client, make_user):
    headers_a = make_user("a4@example.com")
    headers_b = make_user("b4@example.com")

    section = client.post("/sections", json={"name": "Secret"}, headers=headers_a).json()
    document = client.post(
        f"/sections/{section['id']}/documents",
        json={"title": "Notes", "content": "private"},
        headers=headers_a,
    ).json()

    response = client.put(
        f"/documents/{document['id']}",
        json={"title": "Hacked", "content": "hacked"},
        headers=headers_b,
    )
    assert response.status_code in (403, 404)


def test_user_b_cannot_delete_user_a_document(client, make_user):
    headers_a = make_user("a5@example.com")
    headers_b = make_user("b5@example.com")

    section = client.post("/sections", json={"name": "Secret"}, headers=headers_a).json()
    document = client.post(
        f"/sections/{section['id']}/documents",
        json={"title": "Notes", "content": "private"},
        headers=headers_a,
    ).json()

    response = client.delete(f"/documents/{document['id']}", headers=headers_b)
    assert response.status_code in (403, 404)


def test_oversized_document_content_returns_422(client, make_user):
    headers = make_user("oversized@example.com")
    section = client.post("/sections", json={"name": "Big"}, headers=headers).json()

    oversized_content = "x" * (settings.max_document_content_length + 1)
    response = client.post(
        f"/sections/{section['id']}/documents",
        json={"title": "Too big", "content": oversized_content},
        headers=headers,
    )
    assert response.status_code == 422


def test_upload_txt_file_creates_document_with_title_from_filename(client, make_user):
    headers = make_user("upload@example.com")
    section = client.post("/sections", json={"name": "Imports"}, headers=headers).json()

    response = client.post(
        f"/sections/{section['id']}/documents/upload",
        files={"file": ("my-notes.txt", b"Some imported notes", "text/plain")},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["title"] == "my-notes"
    assert response.json()["content"] == "Some imported notes"


def test_upload_md_file_is_accepted(client, make_user):
    headers = make_user("upload-md@example.com")
    section = client.post("/sections", json={"name": "Imports"}, headers=headers).json()

    response = client.post(
        f"/sections/{section['id']}/documents/upload",
        files={"file": ("readme.md", b"# Heading\nBody text", "text/markdown")},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["title"] == "readme"


def test_upload_rejects_unsupported_extension(client, make_user):
    headers = make_user("upload-bad-ext@example.com")
    section = client.post("/sections", json={"name": "Imports"}, headers=headers).json()

    response = client.post(
        f"/sections/{section['id']}/documents/upload",
        files={"file": ("notes.pdf", b"binary-ish content", "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 422


def test_upload_rejects_non_utf8_file(client, make_user):
    headers = make_user("upload-bad-encoding@example.com")
    section = client.post("/sections", json={"name": "Imports"}, headers=headers).json()

    response = client.post(
        f"/sections/{section['id']}/documents/upload",
        files={"file": ("notes.txt", b"\xff\xfe\x00\x01", "text/plain")},
        headers=headers,
    )
    assert response.status_code == 422


def test_upload_rejects_oversized_file(client, make_user):
    headers = make_user("upload-oversized@example.com")
    section = client.post("/sections", json={"name": "Imports"}, headers=headers).json()

    oversized = b"x" * (settings.max_document_content_length + 1)
    response = client.post(
        f"/sections/{section['id']}/documents/upload",
        files={"file": ("notes.txt", oversized, "text/plain")},
        headers=headers,
    )
    assert response.status_code == 422


def test_user_b_cannot_upload_to_user_a_section(client, make_user):
    headers_a = make_user("upload-a@example.com")
    headers_b = make_user("upload-b@example.com")
    section = client.post("/sections", json={"name": "Secret"}, headers=headers_a).json()

    response = client.post(
        f"/sections/{section['id']}/documents/upload",
        files={"file": ("notes.txt", b"sneaky", "text/plain")},
        headers=headers_b,
    )
    assert response.status_code in (403, 404)


def test_max_sections_per_user_returns_422(client, make_user, monkeypatch):
    monkeypatch.setattr(settings, "max_sections_per_user", 1)
    headers = make_user("limit@example.com")

    first = client.post("/sections", json={"name": "One"}, headers=headers)
    assert first.status_code == 201

    second = client.post("/sections", json={"name": "Two"}, headers=headers)
    assert second.status_code == 422
