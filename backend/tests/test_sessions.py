import json

from app.ai.client import get_ai_client
from app.main import app

OPEN_ENDED_QUESTION_JSON = json.dumps(
    [
        {
            "question": "What is the GIL?",
            "category": "technical",
            "theme": "python gil",
            "hint": "Think about thread safety.",
            "explanation": "The GIL serializes bytecode execution across threads.",
        }
    ]
)
QUIZ_QUESTION_JSON = json.dumps(
    [
        {
            "question": "Which keyword defines a coroutine in Python?",
            "category": "technical",
            "options": ["def", "async def", "coroutine", "await"],
            "correct_index": 1,
            "theme": "python coroutines",
            "hint": "It's two words.",
            "explanation": "`async def` declares a coroutine function.",
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


class _StubStreamingAIClient:
    def __init__(self, chunks: list[str]):
        self.chunks = chunks
        self.stream_calls = 0
        self.complete_calls = 0

    async def stream_complete(self, messages, temperature=None):
        self.stream_calls += 1
        for chunk in self.chunks:
            yield chunk

    async def complete(self, messages, temperature=None):
        self.complete_calls += 1
        return ""


def _override_ai_client(stub) -> None:
    app.dependency_overrides[get_ai_client] = lambda: stub


def _clear_ai_override() -> None:
    app.dependency_overrides.pop(get_ai_client, None)


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        if not block:
            continue
        event_line, data_line = block.split("\n", 1)
        events.append((event_line.removeprefix("event: "), json.loads(data_line.removeprefix("data: "))))
    return events


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


def test_quiz_feedback_is_localized_to_user_language(client, make_user):
    headers = make_user("sess-quiz-localized@example.com")
    client.put("/settings/language", json={"language": "uk"}, headers=headers)
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, section_id, "quiz")

    _override_ai_client(_StubAIClient(QUIZ_QUESTION_JSON))
    try:
        client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    correct = client.post(
        f"/sessions/{session_id}/answer", json={"selected_index": 1}, headers=headers
    )
    assert correct.json()["feedback"] == "Правильно!"


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


def test_stream_answer_full_cycle(client, make_user):
    headers = make_user("sess-stream@example.com")
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, section_id, "open_ended")

    _override_ai_client(_StubAIClient(OPEN_ENDED_QUESTION_JSON))
    try:
        client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    stream_chunks = [
        "SCORE: 8\n",
        "FEEDBACK: Solid understanding.\n",
        "STRENGTHS:\n- clear\nGAPS:\n- (none)\n",
    ]
    stub = _StubStreamingAIClient(stream_chunks)
    _override_ai_client(stub)
    try:
        response = client.post(
            f"/sessions/{session_id}/answer/stream",
            json={"answer": "The GIL is a mutex that..."},
            headers=headers,
        )
    finally:
        _clear_ai_override()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(response.text)
    delta_events = [e for e in events if e[0] == "delta"]
    result_events = [e for e in events if e[0] == "result"]

    assert len(delta_events) == len(stream_chunks)
    assert "".join(e[1]["text"] for e in delta_events) == "".join(stream_chunks)
    assert len(result_events) == 1
    result = result_events[0][1]
    assert result["score"] == 8
    assert result["strengths"] == ["clear"]
    assert result["gaps"] == []

    summary = client.get(f"/sessions/{session_id}", headers=headers)
    attempts = summary.json()["attempts"]
    assert attempts[0]["score"] == 8
    assert attempts[0]["answer"] == "The GIL is a mutex that..."


def test_stream_answer_rejected_for_quiz_format(client, make_user):
    headers = make_user("sess-stream-quiz@example.com")
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, section_id, "quiz")

    _override_ai_client(_StubAIClient(QUIZ_QUESTION_JSON))
    try:
        client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    response = client.post(
        f"/sessions/{session_id}/answer/stream", json={"selected_index": 1}, headers=headers
    )
    assert response.status_code == 422


def test_stream_answer_double_submit_does_not_recall_ai(client, make_user):
    headers = make_user("sess-stream-dup@example.com")
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, section_id, "open_ended")

    _override_ai_client(_StubAIClient(OPEN_ENDED_QUESTION_JSON))
    try:
        client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    stub = _StubStreamingAIClient(["SCORE: 6\nFEEDBACK: ok\nSTRENGTHS:\n- (none)\nGAPS:\n- (none)\n"])
    _override_ai_client(stub)
    try:
        first = client.post(
            f"/sessions/{session_id}/answer/stream", json={"answer": "first answer"}, headers=headers
        )
        second = client.post(
            f"/sessions/{session_id}/answer/stream", json={"answer": "second answer"}, headers=headers
        )
    finally:
        _clear_ai_override()

    assert first.status_code == 200
    assert second.status_code == 200
    assert stub.stream_calls == 1

    first_result = _parse_sse(first.text)[-1][1]
    second_result = _parse_sse(second.text)[-1][1]
    assert first_result["score"] == second_result["score"] == 6


def test_new_user_defaults_session_length_to_five(client, make_user):
    headers = make_user("sess-length-default@example.com")
    me = client.get("/auth/me", headers=headers)
    assert me.json()["session_length"] == 5


def test_update_session_length_persists_and_is_used_for_new_sessions(client, make_user):
    headers = make_user("sess-length-update@example.com")
    section_id = _create_section_with_document(client, headers)

    update = client.put("/settings/session-length", json={"session_length": 10}, headers=headers)
    assert update.status_code == 200
    assert update.json()["session_length"] == 10

    session_id = _start_session(client, headers, section_id, "open_ended")
    session = client.get(f"/sessions/{session_id}", headers=headers)
    assert session.json()["target_question_count"] == 10


def test_update_session_length_accepts_only_five_ten_or_fifteen(client, make_user):
    headers = make_user("sess-length-range@example.com")
    for valid in (5, 10, 15):
        response = client.put("/settings/session-length", json={"session_length": valid}, headers=headers)
        assert response.status_code == 200
        assert response.json()["session_length"] == valid

    for invalid in (4, 7, 11, 20):
        response = client.put("/settings/session-length", json={"session_length": invalid}, headers=headers)
        assert response.status_code == 422


def test_next_question_reports_progress_and_blocks_past_the_target_count(client, make_user, monkeypatch):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "question_bank_batch_size", 1)
    headers = make_user("sess-length-cap@example.com")
    length_update = client.put("/settings/session-length", json={"session_length": 5}, headers=headers)
    assert length_update.status_code == 200
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, section_id, "open_ended")

    _override_ai_client(_StubAIClient(OPEN_ENDED_QUESTION_JSON))
    try:
        responses = [client.post(f"/sessions/{session_id}/next", headers=headers) for _ in range(6)]
    finally:
        _clear_ai_override()

    first, *_, fifth, sixth = responses
    assert first.json()["question_number"] == 1
    assert first.json()["total_questions"] == 5
    assert fifth.json()["question_number"] == 5
    assert sixth.status_code == 409


def test_start_session_blocked_when_live_generation_disabled_and_pool_empty(client, make_user, monkeypatch):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "live_question_generation_enabled", False)
    headers = make_user("sess-live-gen-disabled@example.com")
    section_id = _create_section_with_document(client, headers)

    # No questions in the bank for this combination, so the session must be
    # rejected up front (rather than created and failing on its first /next),
    # with the failing parameters - crucially incl. language - echoed back.
    response = client.post(
        "/sessions",
        json={"section_ids": [section_id], "mode": "technical", "format": "open_ended"},
        headers=headers,
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "no_questions"
    assert detail["mode"] == "technical"
    assert detail["format"] == "open_ended"
    assert detail["language"] == "en"


def test_next_question_blocked_when_pool_exhausted_mid_session(client, make_user, monkeypatch):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "live_question_generation_enabled", False)
    headers = make_user("sess-pool-exhausted@example.com")
    section_id = _create_section_with_document(client, headers)

    # Seed a single question so the session can start, then exhaust it - the
    # next /next finds the pool empty and (live generation off) must refuse to
    # silently generate, pointing the user back to the Question Bank instead.
    _override_ai_client(_StubAIClient(OPEN_ENDED_QUESTION_JSON))
    try:
        generate_resp = client.post(
            "/question-bank/generate",
            json={"section_ids": [section_id], "mode": "technical", "format": "open_ended", "count": 1},
            headers=headers,
        )
    finally:
        _clear_ai_override()
    assert generate_resp.status_code == 201

    session_id = _start_session(client, headers, section_id, "open_ended")
    assert client.post(f"/sessions/{session_id}/next", headers=headers).status_code == 200

    stub = _StubAIClient(OPEN_ENDED_QUESTION_JSON)
    _override_ai_client(stub)
    try:
        response = client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    assert response.status_code == 503
    assert "Question Bank" in response.json()["detail"]
    assert stub.calls == 0


def test_next_question_uses_pregenerated_bank_row_when_live_generation_disabled(client, make_user, monkeypatch):
    from app.config import settings as app_settings

    monkeypatch.setattr(app_settings, "live_question_generation_enabled", False)
    headers = make_user("sess-live-gen-disabled-prefilled@example.com")
    section_id = _create_section_with_document(client, headers)

    _override_ai_client(_StubAIClient(OPEN_ENDED_QUESTION_JSON))
    try:
        generate_resp = client.post(
            "/question-bank/generate",
            json={"section_ids": [section_id], "mode": "technical", "format": "open_ended", "count": 1},
            headers=headers,
        )
    finally:
        _clear_ai_override()
    assert generate_resp.status_code == 201

    session_id = _start_session(client, headers, section_id, "open_ended")

    stub = _StubAIClient(OPEN_ENDED_QUESTION_JSON)
    _override_ai_client(stub)
    try:
        next_resp = client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    assert next_resp.status_code == 200
    assert next_resp.json()["question"] == "What is the GIL?"
    assert stub.calls == 0


def test_finish_requires_auth(client):
    response = client.post("/sessions/1/finish")
    assert response.status_code == 401


def test_finish_rejects_another_users_session(client, make_user):
    headers_a = make_user("sess-finish-a@example.com")
    headers_b = make_user("sess-finish-b@example.com")
    section_id = _create_section_with_document(client, headers_a)
    session_id = _start_session(client, headers_a, section_id, "open_ended")

    response = client.post(f"/sessions/{session_id}/finish", headers=headers_b)
    assert response.status_code == 404


def test_finish_sets_timestamp_and_is_idempotent(client, make_user):
    headers = make_user("sess-finish@example.com")
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, section_id, "open_ended")

    first = client.post(f"/sessions/{session_id}/finish", headers=headers)
    assert first.status_code == 200
    assert first.json()["finished_at"] is not None

    second = client.post(f"/sessions/{session_id}/finish", headers=headers)
    assert second.status_code == 200
    assert second.json()["finished_at"] == first.json()["finished_at"]


def test_next_question_rejected_after_finish(client, make_user):
    headers = make_user("sess-finish-next@example.com")
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, section_id, "open_ended")

    client.post(f"/sessions/{session_id}/finish", headers=headers)
    response = client.post(f"/sessions/{session_id}/next", headers=headers)
    assert response.status_code == 409


def test_answer_rejected_for_new_attempt_after_finish_but_existing_result_still_readable(
    client, make_user
):
    headers = make_user("sess-finish-answer@example.com")
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, section_id, "quiz")

    _override_ai_client(_StubAIClient(QUIZ_QUESTION_JSON))
    try:
        client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    client.post(f"/sessions/{session_id}/finish", headers=headers)

    blocked = client.post(f"/sessions/{session_id}/answer", json={"selected_index": 1}, headers=headers)
    assert blocked.status_code == 409


def test_answer_stream_rejected_after_finish(client, make_user):
    headers = make_user("sess-finish-stream@example.com")
    section_id = _create_section_with_document(client, headers)
    session_id = _start_session(client, headers, section_id, "open_ended")

    _override_ai_client(_StubAIClient(OPEN_ENDED_QUESTION_JSON))
    try:
        client.post(f"/sessions/{session_id}/next", headers=headers)
    finally:
        _clear_ai_override()

    client.post(f"/sessions/{session_id}/finish", headers=headers)

    response = client.post(
        f"/sessions/{session_id}/answer/stream", json={"answer": "test"}, headers=headers
    )
    assert response.status_code == 409
