import json

from app.ai.client import get_ai_client
from app.main import app

OPEN_ENDED_QUESTION_JSON = json.dumps([{"question": "What is the GIL?", "category": "technical"}])
QUIZ_QUESTION_JSON = json.dumps(
    [
        {
            "question": "Which keyword defines a coroutine in Python?",
            "category": "technical",
            "options": ["def", "async def", "coroutine", "await"],
            "correct_index": 1,
        }
    ]
)


class _StubAIClient:
    def __init__(self, response_text: str):
        self.response_text = response_text
        self.calls = 0

    async def complete(self, messages: list[dict[str, str]], temperature: float | None = None) -> str:
        self.calls += 1
        return self.response_text


def _override_ai_client(stub) -> None:
    app.dependency_overrides[get_ai_client] = lambda: stub


def _clear_ai_override() -> None:
    app.dependency_overrides.pop(get_ai_client, None)


def _create_section_with_document(client, headers) -> int:
    section = client.post("/sections", json={"name": "Python"}, headers=headers).json()
    client.post(
        f"/sections/{section['id']}/documents",
        json={"title": "Notes", "content": "Some interview prep notes about Python."},
        headers=headers,
    )
    return section["id"]


def _start_session(client, headers, section_id: int, fmt: str) -> int:
    response = client.post(
        "/sessions",
        json={"section_ids": [section_id], "mode": "technical", "format": fmt},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_open_ended_full_cycle(client, make_user):
    headers = make_user("sess-open@example.com")
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, section_id, "open_ended")

    _override_ai_client(_StubAIClient(OPEN_ENDED_QUESTION_JSON))
    try:
        next_resp = client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    assert next_resp.status_code == 200
    body = next_resp.json()
    assert body["question"] == "What is the GIL?"
    assert body["options"] is None

    evaluation_json = json.dumps(
        {"score": 8, "feedback": "Good answer.", "strengths": ["clear"], "gaps": []}
    )
    _override_ai_client(_StubAIClient(evaluation_json))
    try:
        answer_resp = client.post(
            f"/sessions/{session_id}/answer",
            json={"answer": "The GIL is a mutex that..."},
            headers=headers,
        )
    finally:
        _clear_ai_override()

    assert answer_resp.status_code == 200
    result = answer_resp.json()
    assert result["score"] == 8
    assert result["strengths"] == ["clear"]

    summary = client.get(f"/sessions/{session_id}", headers=headers)
    assert summary.status_code == 200
    attempts = summary.json()["attempts"]
    assert len(attempts) == 1
    assert attempts[0]["score"] == 8
    assert attempts[0]["answer"] == "The GIL is a mutex that..."
    assert summary.json()["average_score"] == 8


def test_quiz_correct_answer_scores_ten(client, make_user):
    headers = make_user("sess-quiz-correct@example.com")
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, section_id, "quiz")

    _override_ai_client(_StubAIClient(QUIZ_QUESTION_JSON))
    try:
        next_resp = client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    assert next_resp.status_code == 200
    body = next_resp.json()
    assert body["options"] == ["def", "async def", "coroutine", "await"]
    assert "correct_index" not in body

    result = client.post(
        f"/sessions/{session_id}/answer", json={"selected_index": 1}, headers=headers
    )
    assert result.status_code == 200
    data = result.json()
    assert data["score"] == 10
    assert data["is_correct"] is True
    assert data["correct_index"] == 1


def test_quiz_wrong_answer_scores_zero(client, make_user):
    headers = make_user("sess-quiz-wrong@example.com")
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, section_id, "quiz")

    _override_ai_client(_StubAIClient(QUIZ_QUESTION_JSON))
    try:
        client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    result = client.post(
        f"/sessions/{session_id}/answer", json={"selected_index": 0}, headers=headers
    )
    assert result.status_code == 200
    data = result.json()
    assert data["score"] == 0
    assert data["is_correct"] is False
    assert data["correct_index"] == 1


def test_quiz_summary_hides_correct_index_before_answering(client, make_user):
    headers = make_user("sess-quiz-hide@example.com")
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, section_id, "quiz")

    _override_ai_client(_StubAIClient(QUIZ_QUESTION_JSON))
    try:
        client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    summary = client.get(f"/sessions/{session_id}", headers=headers)
    attempts = summary.json()["attempts"]
    assert len(attempts) == 1
    assert attempts[0]["correct_index"] is None
    assert attempts[0]["score"] is None


def test_user_sees_only_their_own_sessions(client, make_user):
    headers_a = make_user("sess-a@example.com")
    headers_b = make_user("sess-b@example.com")
    section_id = _create_section_with_document(client, headers_a)
    _start_session(client, headers_a, section_id, "open_ended")

    list_b = client.get("/sessions", headers=headers_b)
    assert list_b.status_code == 200
    assert list_b.json() == []

    list_a = client.get("/sessions", headers=headers_a)
    assert len(list_a.json()) == 1


def test_user_b_cannot_view_user_a_session(client, make_user):
    headers_a = make_user("sess-c1@example.com")
    headers_b = make_user("sess-c2@example.com")
    section_id = _create_section_with_document(client, headers_a)
    session_id = _start_session(client, headers_a, section_id, "open_ended")

    response = client.get(f"/sessions/{session_id}", headers=headers_b)
    assert response.status_code in (403, 404)


def test_double_submit_does_not_double_score_open_ended(client, make_user):
    headers = make_user("sess-dup-open@example.com")
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, section_id, "open_ended")

    _override_ai_client(_StubAIClient(OPEN_ENDED_QUESTION_JSON))
    try:
        client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    eval_stub = _StubAIClient(
        json.dumps({"score": 7, "feedback": "Solid.", "strengths": ["x"], "gaps": []})
    )
    _override_ai_client(eval_stub)
    try:
        first = client.post(
            f"/sessions/{session_id}/answer", json={"answer": "answer one"}, headers=headers
        )
        second = client.post(
            f"/sessions/{session_id}/answer",
            json={"answer": "a totally different answer"},
            headers=headers,
        )
    finally:
        _clear_ai_override()

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["score"] == second.json()["score"] == 7
    assert eval_stub.calls == 1


def test_double_submit_does_not_double_score_quiz(client, make_user):
    headers = make_user("sess-dup-quiz@example.com")
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, section_id, "quiz")

    _override_ai_client(_StubAIClient(QUIZ_QUESTION_JSON))
    try:
        client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    first = client.post(f"/sessions/{session_id}/answer", json={"selected_index": 1}, headers=headers)
    second = client.post(f"/sessions/{session_id}/answer", json={"selected_index": 0}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["score"] == second.json()["score"] == 10
