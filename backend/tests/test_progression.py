from fastapi.testclient import TestClient

from app.models import Equipment
from app.services.progression import step_weight


def _start(client: TestClient, name: str, day: str) -> dict:
    templates = {t["name"]: t for t in client.get("/api/workout-templates").json()}
    response = client.post("/api/workout-sessions",
                           json={"workout_template_id": templates[name]["id"], "performed_on": day})
    assert response.status_code == 201, response.text
    return response.json()


def _do(client: TestClient, session: dict, exercise_id: str, reps: list[int], weight: float | None = None) -> None:
    exercise = next(e for e in session["exercises"] if e["exercise_id"] == exercise_id)
    for s, r in zip(exercise["sets"], reps, strict=True):
        body = {"repetitions": r, "completed": True}
        if weight is not None:
            body["weight"] = weight
        client.patch(f"/api/workout-sessions/{session['id']}/sets/{s['id']}", json=body)
    client.post(f"/api/workout-sessions/{session['id']}/complete", json={})


def _bench(session: dict) -> dict:
    return next(e for e in session["exercises"] if e["exercise_id"] == "EX0001")


def test_step_weight_uses_available_dumbbells() -> None:
    dumbbells = Equipment(slug="d", name="D", equipment_type="dumbbell", available_weights=[5, 10, 12.5, 15, 20])
    assert step_weight(dumbbells, 12.5, 1) == 15
    assert step_weight(dumbbells, 12.5, -1) == 10
    assert step_weight(dumbbells, 20, 1) == 20  # heaviest available
    assert step_weight(dumbbells, 11, 1) == 12.5  # off-list weights snap to the next option
    plates = Equipment(slug="p", name="P", equipment_type="cable", weight_increment=2.5)
    assert step_weight(plates, 20, 1) == 22.5


def test_top_of_range_suggests_increase_without_applying(client: TestClient) -> None:
    _do(client, _start(client, "Upper A", "2026-10-19"), "EX0001", [10, 10])
    bench = _bench(_start(client, "Upper A", "2026-10-26"))
    assert bench["suggestion_action"] == "increase"
    assert bench["recommended_weight"] == 25  # next dumbbell
    # Not applied automatically: sets still use last time's weight.
    assert {s["weight"] for s in bench["sets"]} == {20}


def test_apply_weight_requires_explicit_action(client: TestClient) -> None:
    _do(client, _start(client, "Upper A", "2026-10-19"), "EX0001", [10, 10])
    session = _start(client, "Upper A", "2026-10-26")
    bench = _bench(session)
    first = bench["sets"][0]
    client.patch(f"/api/workout-sessions/{session['id']}/sets/{first['id']}", json={"completed": True})
    applied = client.post(f"/api/workout-sessions/{session['id']}/exercises/{bench['id']}/apply-weight",
                          json={"weight": 25}).json()
    # Completed sets are never rewritten.
    assert [s["weight"] for s in applied["sets"]] == [20, 25]


def test_within_range_maintains(client: TestClient) -> None:
    _do(client, _start(client, "Upper A", "2026-10-19"), "EX0001", [10, 8])
    bench = _bench(_start(client, "Upper A", "2026-10-26"))
    assert bench["suggestion_action"] == "maintain"
    assert bench["recommended_weight"] == 20


def test_big_drop_suggests_decrease(client: TestClient) -> None:
    _do(client, _start(client, "Upper A", "2026-10-19"), "EX0001", [5, 5])
    bench = _bench(_start(client, "Upper A", "2026-10-26"))
    assert bench["suggestion_action"] == "decrease"
    assert bench["recommended_weight"] == 15
    assert {s["weight"] for s in bench["sets"]} == {20}


def test_suggestions_respect_custom_dumbbell_set(client: TestClient) -> None:
    dumbbells = next(e for e in client.get("/api/equipment").json() if e["slug"] == "dumbbells")
    client.patch(f"/api/equipment/{dumbbells['id']}", json={"available_weights": [15, 20, 22.5, 30]})
    _do(client, _start(client, "Upper A", "2026-10-19"), "EX0001", [10, 10])
    bench = _bench(_start(client, "Upper A", "2026-10-26"))
    assert bench["recommended_weight"] == 22.5


def test_variations_do_not_share_history(client: TestClient) -> None:
    _do(client, _start(client, "Upper A", "2026-10-19"), "EX0001", [10, 10], weight=30)
    incline = _start(client, "Upper B", "2026-10-22")["exercises"][0]
    assert incline["exercise_id"] == "EX0005"
    assert incline["previous"] is None
    assert incline["suggestion_action"] == "start"
    assert {s["weight"] for s in incline["sets"]} == {15}


def test_plan_weight_edit_overrides_history(client: TestClient) -> None:
    _do(client, _start(client, "Upper A", "2026-10-19"), "EX0001", [9, 9])
    template = next(t for t in client.get("/api/workout-templates").json() if t["name"] == "Upper A")
    te = template["exercises"][0]
    client.patch(f"/api/workout-templates/{template['id']}/exercises/{te['id']}", json={"suggested_weight": 30})
    bench = _bench(_start(client, "Upper A", "2026-10-26"))
    assert bench["suggestion_action"] == "plan"
    assert {s["weight"] for s in bench["sets"]} == {30}


def test_exercise_progress(client: TestClient) -> None:
    _do(client, _start(client, "Upper A", "2026-10-19"), "EX0001", [10, 10])
    _do(client, _start(client, "Upper A", "2026-10-26"), "EX0001", [8, 8], weight=25)
    progress = client.get("/api/exercises/EX0001/progress").json()
    assert progress["sessions"] == 2
    assert progress["best_weight"] == 25
    assert [p["top_weight"] for p in progress["points"]] == [20, 25]
    assert progress["total_volume"] == 20 * 20 + 25 * 16
    assert progress["history"][0]["performed_on"] == "2026-10-26"

    summary = client.get("/api/analytics/summary", params={"date": "2026-10-27"}).json()
    assert summary["total_workouts"] == 2
    assert summary["personal_bests"][0]["weight"] == 25
    assert summary["personal_bests"][0]["previous_best"] == 20
