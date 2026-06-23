from datetime import datetime, timezone

import pytest

from app.models import Attempt
from app.models import Session as TrainingSession


def _user_id(client, headers) -> int:
    return client.get("/auth/me", headers=headers).json()["id"]


def _make_session_with_attempts(db_session, user_id, section_ids, scored_attempts):
    session = TrainingSession(
        user_id=user_id, mode="technical", format="open_ended", section_ids=section_ids
    )
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)

    for score, created_at in scored_attempts:
        db_session.add(
            Attempt(
                session_id=session.id,
                question="Q",
                category="technical",
                format="open_ended",
                answer="A",
                score=score,
                created_at=created_at,
            )
        )
    db_session.commit()
    return session


def test_stats_empty_for_new_user(client, make_user):
    headers = make_user("stats-empty@example.com")
    response = client.get("/sessions/stats", headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "total_attempts": 0,
        "average_score": None,
        "score_history": [],
        "weakest_topics": [],
    }


def test_stats_aggregates_score_history_and_weakest_topics(client, make_user, db_session):
    headers = make_user("stats-agg@example.com")
    user_id = _user_id(client, headers)

    python_section = client.post("/sections", json={"name": "Python"}, headers=headers).json()
    system_design_section = client.post(
        "/sections", json={"name": "System Design"}, headers=headers
    ).json()

    t0 = datetime(2024, 1, 1, tzinfo=timezone.utc)
    _make_session_with_attempts(
        db_session,
        user_id,
        [python_section["id"]],
        [(8, t0), (6, t0.replace(day=2))],
    )
    _make_session_with_attempts(
        db_session,
        user_id,
        [system_design_section["id"]],
        [(2, t0.replace(day=3))],
    )

    response = client.get("/sessions/stats", headers=headers)
    assert response.status_code == 200
    body = response.json()

    assert body["total_attempts"] == 3
    assert body["average_score"] == pytest.approx((8 + 6 + 2) / 3)
    assert [point["score"] for point in body["score_history"]] == [8, 6, 2]

    topics = {topic["section_name"]: topic for topic in body["weakest_topics"]}
    assert topics["System Design"]["average_score"] == pytest.approx(2)
    assert topics["Python"]["average_score"] == pytest.approx((8 + 6) / 2)
    assert body["weakest_topics"][0]["section_name"] == "System Design"


def test_stats_weakest_topics_capped_at_five(client, make_user, db_session):
    headers = make_user("stats-cap@example.com")
    user_id = _user_id(client, headers)

    for i in range(6):
        section = client.post("/sections", json={"name": f"Topic {i}"}, headers=headers).json()
        _make_session_with_attempts(
            db_session, user_id, [section["id"]], [(i, datetime(2024, 1, i + 1, tzinfo=timezone.utc))]
        )

    response = client.get("/sessions/stats", headers=headers)
    weakest_topics = response.json()["weakest_topics"]
    assert len(weakest_topics) == 5
    assert weakest_topics[0]["section_name"] == "Topic 0"


def test_stats_are_isolated_per_user(client, make_user, db_session):
    headers_a = make_user("stats-a@example.com")
    headers_b = make_user("stats-b@example.com")
    user_id_a = _user_id(client, headers_a)

    section = client.post("/sections", json={"name": "Python"}, headers=headers_a).json()
    _make_session_with_attempts(
        db_session, user_id_a, [section["id"]], [(5, datetime(2024, 1, 1, tzinfo=timezone.utc))]
    )

    response_b = client.get("/sessions/stats", headers=headers_b)
    assert response_b.json() == {
        "total_attempts": 0,
        "average_score": None,
        "score_history": [],
        "weakest_topics": [],
    }
