from fastapi.testclient import TestClient

from tests.conftest import ABBY
from tests.test_sessions import MONDAY, NEXT_MONDAY, _complete_all, _start

AS_ABBY = {"X-Profile-Id": str(ABBY)}


def test_profiles_listed(client: TestClient) -> None:
    assert client.get("/api/profiles").json() == [{"id": 1, "name": "Trey", "email": None}, {"id": 2, "name": "Abby", "email": None}]


def test_profile_header_required(client: TestClient) -> None:
    assert client.get("/api/dashboard", headers={"X-Profile-Id": ""}).status_code == 422
    assert client.get("/api/dashboard", headers={"X-Profile-Id": "99"}).status_code == 404
    client.headers.pop("X-Profile-Id")
    assert client.get("/api/dashboard").status_code == 400
    # The shared library doesn't need one... except where it reports per-person data.
    assert client.get("/api/equipment").status_code == 200


def test_new_profile_starts_without_a_plan(client: TestClient) -> None:
    dashboard = client.get("/api/dashboard", params={"date": MONDAY}, headers=AS_ABBY).json()
    assert dashboard["today"] is None
    assert dashboard["templates"] == []
    assert dashboard["last_session"] is None
    assert dashboard["program_week"] is None
    assert client.get("/api/workout-templates", headers=AS_ABBY).json() == []
    assert client.get("/api/history", headers=AS_ABBY).json() == {"total": 0, "items": []}
    assert client.get("/api/analytics/summary", params={"date": MONDAY}, headers=AS_ABBY).json()["total_workouts"] == 0
    # The exercise library is shared, but "scheduled in" reflects her (empty) plan.
    bench = client.get("/api/exercises/EX0001", headers=AS_ABBY).json()
    assert bench["name"] == "Flat dumbbell bench press"
    assert not bench["scheduled_in"]


def test_plans_are_separate(client: TestClient) -> None:
    trey_upper = client.get("/api/workout-templates").json()[0]
    assert client.get(f"/api/workout-templates/{trey_upper['id']}", headers=AS_ABBY).status_code == 404
    # Same name and weekday as one of Trey's workouts is fine for Abby, and doesn't move his.
    created = client.post("/api/workout-templates", json={"name": "Upper A", "weekday": 0}, headers=AS_ABBY)
    assert created.status_code == 201, created.text
    assert [t["name"] for t in client.get("/api/workout-templates", headers=AS_ABBY).json()] == ["Upper A"]
    assert client.get(f"/api/workout-templates/{trey_upper['id']}").json()["weekday"] == 0
    # Copying from someone else's workout is not allowed.
    copy = client.post("/api/workout-templates", json={"name": "Copy", "copy_from_template_id": trey_upper["id"]},
                       headers=AS_ABBY)
    assert copy.status_code == 404
    assert client.post("/api/workout-sessions", json={"workout_template_id": trey_upper["id"]},
                       headers=AS_ABBY).status_code == 422


def test_sessions_history_and_progression_are_separate(client: TestClient) -> None:
    trey = _start(client)
    _complete_all(client, trey, reps=10)

    # Abby can't open or edit Trey's workout.
    assert client.get(f"/api/workout-sessions/{trey['id']}", headers=AS_ABBY).status_code == 404
    set_id = trey["exercises"][0]["sets"][0]["id"]
    assert client.patch(f"/api/workout-sessions/{trey['id']}/sets/{set_id}", json={"repetitions": 1},
                        headers=AS_ABBY).status_code == 404

    # Her first bench press has no history and no weight suggestion from his.
    abby = client.post("/api/workout-sessions", json={"performed_on": NEXT_MONDAY}, headers=AS_ABBY).json()
    bench = client.post(f"/api/workout-sessions/{abby['id']}/exercises", json={"exercise_id": "EX0001"},
                        headers=AS_ABBY).json()
    assert bench["previous"] is None
    assert bench["suggestion_action"] == "start"
    assert client.get("/api/history", headers=AS_ABBY).json()["total"] == 0
    assert client.get("/api/exercises/EX0001/progress", headers=AS_ABBY).json()["sessions"] == 0
    assert client.get("/api/exercises/EX0001/progress").json()["sessions"] == 1


def test_active_sessions_are_per_profile(client: TestClient) -> None:
    abby = client.post("/api/workout-sessions", json={"performed_on": MONDAY}, headers=AS_ABBY)
    assert abby.status_code == 201
    assert client.get("/api/workout-sessions/active").json() is None
    trey = _start(client)  # not blocked by Abby's workout
    assert client.get("/api/workout-sessions/active").json()["id"] == trey["id"]
    assert client.get("/api/workout-sessions/active", headers=AS_ABBY).json()["id"] == abby.json()["id"]


def test_settings_are_per_profile(client: TestClient) -> None:
    _start(client)  # sets Trey's program start date
    assert client.get("/api/settings").json()["program_start_date"] == MONDAY
    abby = client.get("/api/settings", headers=AS_ABBY).json()
    assert abby["program_start_date"] is None
    client.patch("/api/settings", json={"rest_timer_sound": False}, headers=AS_ABBY)
    assert client.get("/api/settings").json()["rest_timer_sound"] is True
    assert client.get("/api/settings", headers=AS_ABBY).json()["rest_timer_sound"] is False


def test_plan_import_into_another_profile(client: TestClient, seeded, data_dir, plan_zip) -> None:  # noqa: ANN001
    from app.services.importer import run_import

    report = run_import(seeded, library_path=None, plan_path=plan_zip, media_dir=data_dir / "media", profile_id=ABBY)
    assert report.templates_created == 4  # all new for her
    abby = {t["name"] for t in client.get("/api/workout-templates", headers=AS_ABBY).json()}
    trey = {t["name"] for t in client.get("/api/workout-templates").json()}
    assert abby == trey == {"Upper A", "Lower A", "Upper B", "Cardio Mobility"}
