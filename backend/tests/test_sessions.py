from fastapi.testclient import TestClient

MONDAY = "2026-10-19"
NEXT_MONDAY = "2026-10-26"


def _templates(client: TestClient) -> dict[str, dict]:
    return {t["name"]: t for t in client.get("/api/workout-templates").json()}


def _start(client: TestClient, name: str = "Upper A", day: str = MONDAY) -> dict:
    template_id = _templates(client)[name]["id"]
    response = client.post("/api/workout-sessions", json={"workout_template_id": template_id, "performed_on": day})
    assert response.status_code == 201, response.text
    return response.json()


def _complete_all(client: TestClient, session: dict, reps: int | None = None, weight: float | None = None) -> None:
    for exercise in session["exercises"]:
        for s in exercise["sets"]:
            body: dict = {"completed": True}
            if reps is not None and exercise["tracking_type"] == "strength":
                body["repetitions"] = reps
            if weight is not None and exercise["exercise_id"] == "EX0001":
                body["weight"] = weight
            assert client.patch(f"/api/workout-sessions/{session['id']}/sets/{s['id']}", json=body).status_code == 200
    assert client.post(f"/api/workout-sessions/{session['id']}/complete", json={}).status_code == 200


def test_dashboard_shows_todays_workout(client: TestClient) -> None:
    data = client.get("/api/dashboard", params={"date": MONDAY}).json()
    assert data["weekday_name"] == "Monday"
    assert data["today"]["name"] == "Upper A"
    assert data["today"]["exercise_count"] == 2
    assert data["active_session"] is None

    sunday = client.get("/api/dashboard", params={"date": "2026-10-18"}).json()
    assert sunday["today"] is None  # rest day


def test_create_session_snapshots_plan_and_prefills_sets(client: TestClient) -> None:
    session = _start(client)
    assert session["status"] == "in_progress"
    assert session["program_week"] == 1
    bench, fly = session["exercises"]
    assert bench["exercise_name"] == "Flat dumbbell bench press"
    assert bench["target_sets"] == 2  # ramp-in weeks use sets_week_1_2
    assert bench["suggestion_action"] == "start"
    assert [(s["weight"], s["repetitions"], s["completed"]) for s in bench["sets"]] == [(20, 8, False)] * 2
    assert bench["load_type"] == "per_dumbbell"
    assert bench["thumb_url"].endswith("ex0001.webp")
    # Unilateral exercise: a left and right row for each set.
    assert [(s["set_number"], s["side"]) for s in fly["sets"]] == [(1, "left"), (1, "right"), (2, "left"), (2, "right")]
    assert fly["pulley_ratio"] == "2:1"


def test_only_one_active_session(client: TestClient) -> None:
    session = _start(client)
    response = client.post("/api/workout-sessions", json={"workout_template_id": session["workout_template_id"]})
    assert response.status_code == 409
    assert response.json()["detail"]["active_session_id"] == session["id"]
    assert client.get("/api/workout-sessions/active").json()["id"] == session["id"]


def test_saving_and_updating_sets_persists(client: TestClient) -> None:
    session = _start(client)
    set_id = session["exercises"][0]["sets"][0]["id"]
    url = f"/api/workout-sessions/{session['id']}/sets/{set_id}"

    saved = client.patch(url, json={"weight": 25, "repetitions": 10, "completed": True}).json()
    assert saved["completed"] is True and saved["completed_at"] is not None

    updated = client.patch(url, json={"repetitions": 9}).json()
    assert (updated["weight"], updated["repetitions"], updated["completed"]) == (25, 9, True)

    # A "refresh": reloading the session returns everything saved so far.
    reloaded = client.get(f"/api/workout-sessions/{session['id']}").json()
    first = reloaded["exercises"][0]["sets"][0]
    assert (first["weight"], first["repetitions"], first["completed"]) == (25, 9, True)
    assert reloaded["completed_sets"] == 1


def test_set_validation(client: TestClient) -> None:
    session = _start(client)
    set_id = session["exercises"][0]["sets"][0]["id"]
    url = f"/api/workout-sessions/{session['id']}/sets/{set_id}"
    assert client.patch(url, json={"weight": -5}).status_code == 422
    assert client.patch(url, json={"repetitions": 9999}).status_code == 422
    assert client.patch(f"/api/workout-sessions/{session['id']}/sets/999999", json={"weight": 5}).status_code == 404
    bad = client.post(f"/api/workout-sessions/{session['id']}/exercises", json={"exercise_id": "EX9999"})
    assert bad.status_code == 422


def test_add_and_delete_sets(client: TestClient) -> None:
    session = _start(client)
    bench, fly = session["exercises"]
    created = client.post(f"/api/workout-sessions/{session['id']}/exercises/{bench['id']}/sets").json()
    assert [s["set_number"] for s in created] == [3]
    pair = client.post(f"/api/workout-sessions/{session['id']}/exercises/{fly['id']}/sets").json()
    assert [(s["set_number"], s["side"]) for s in pair] == [(3, "left"), (3, "right")]

    # Deleting set 1 of the unilateral exercise removes both sides and renumbers.
    first_left = fly["sets"][0]["id"]
    assert client.delete(f"/api/workout-sessions/{session['id']}/sets/{first_left}").status_code == 204
    fly_now = client.get(f"/api/workout-sessions/{session['id']}").json()["exercises"][1]
    assert [(s["set_number"], s["side"]) for s in fly_now["sets"]] == [(1, "left"), (1, "right"), (2, "left"), (2, "right")]


def test_complete_and_history(client: TestClient) -> None:
    session = _start(client)
    _complete_all(client, session, reps=10)
    response = client.post(f"/api/workout-sessions/{session['id']}/complete", json={})
    assert response.status_code == 409  # already completed

    history = client.get("/api/history").json()
    assert history["total"] == 1
    item = history["items"][0]
    assert item["name"] == "Upper A"
    assert item["completed_sets"] == 6
    assert item["duration_minutes"] is not None
    assert item["exercises"][0]["best"] == "20 lb × 10"
    assert client.get("/api/workout-sessions/active").json() is None


def test_previous_performance_shown_next_time(client: TestClient) -> None:
    first = _start(client)
    _complete_all(client, first, reps=9)
    second = _start(client, day=NEXT_MONDAY)
    bench = second["exercises"][0]
    assert bench["previous"]["session_id"] == first["id"]
    assert bench["previous"]["summary"] == "20 lb × 9, 9"
    # Prefilled from last time.
    assert [(s["weight"], s["repetitions"]) for s in bench["sets"]] == [(20, 9), (20, 9)]


def test_edit_completed_session(client: TestClient) -> None:
    session = _start(client)
    _complete_all(client, session, reps=10)
    set_id = session["exercises"][0]["sets"][1]["id"]
    fixed = client.patch(f"/api/workout-sessions/{session['id']}/sets/{set_id}", json={"repetitions": 7}).json()
    assert fixed["repetitions"] == 7
    patched = client.patch(f"/api/workout-sessions/{session['id']}", json={"notes": "Felt strong"}).json()
    assert patched["notes"] == "Felt strong"
    assert patched["status"] == "completed"


def test_template_changes_do_not_alter_history(client: TestClient) -> None:
    session = _start(client)
    _complete_all(client, session, reps=10)
    before = client.get(f"/api/workout-sessions/{session['id']}").json()

    template = _templates(client)["Upper A"]
    te = template["exercises"][0]
    client.patch(f"/api/workout-templates/{template['id']}/exercises/{te['id']}",
                 json={"target_sets": 5, "target_rep_min": 3, "target_rep_max": 5, "suggested_weight": 40})
    client.patch(f"/api/exercises/EX0001", json={"name": "Renamed bench"})
    client.delete(f"/api/workout-templates/{template['id']}/exercises/{template['exercises'][1]['id']}")
    after_edit = client.get(f"/api/workout-sessions/{session['id']}").json()
    for key in ("exercise_name", "target_sets", "target_rep_min", "target_rep_max", "sets"):
        assert after_edit["exercises"][0][key] == before["exercises"][0][key]
    assert len(after_edit["exercises"]) == 2

    assert client.delete(f"/api/workout-templates/{template['id']}").status_code == 204
    after_delete = client.get(f"/api/workout-sessions/{session['id']}").json()
    assert after_delete["workout_template_id"] is None
    assert after_delete["name"] == "Upper A"
    assert after_delete["exercises"][0]["sets"] == before["exercises"][0]["sets"]


def test_skipped_template_exercise_not_in_new_session(client: TestClient) -> None:
    template = _templates(client)["Upper A"]
    fly = template["exercises"][1]
    client.patch(f"/api/workout-templates/{template['id']}/exercises/{fly['id']}", json={"skipped": True})
    session = _start(client)
    assert [e["exercise_id"] for e in session["exercises"]] == ["EX0001"]


def test_perform_another_days_workout(client: TestClient) -> None:
    # Monday, but doing Thursday's workout. The schedule is unchanged.
    session = _start(client, name="Upper B", day=MONDAY)
    assert session["name"] == "Upper B"
    assert _templates(client)["Upper B"]["weekday"] == 3


def test_discard_session(client: TestClient) -> None:
    session = _start(client)
    assert client.delete(f"/api/workout-sessions/{session['id']}").status_code == 204
    assert client.get(f"/api/workout-sessions/{session['id']}").status_code == 404


def test_cardio_and_timed_sets(client: TestClient) -> None:
    lower = _start(client, name="Lower A", day="2026-10-20")
    plank = lower["exercises"][1]
    assert plank["tracking_type"] == "timed"
    assert plank["sets"][0]["duration_seconds"] == 20
    client.post(f"/api/workout-sessions/{lower['id']}/complete", json={})

    cardio = _start(client, name="Cardio Mobility", day="2026-10-24")
    walk = cardio["exercises"][0]
    assert walk["tracking_type"] == "cardio"
    s = walk["sets"][0]
    assert s["duration_seconds"] == 1800
    saved = client.patch(f"/api/workout-sessions/{cardio['id']}/sets/{s['id']}",
                         json={"duration_seconds": 2100, "distance": 2.1, "speed": 3.6, "completed": True}).json()
    assert (saved["distance"], saved["speed"]) == (2.1, 3.6)
