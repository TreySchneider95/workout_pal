from fastapi.testclient import TestClient


def _templates(client: TestClient) -> dict[str, dict]:
    return {t["name"]: t for t in client.get("/api/workout-templates").json()}


def test_move_workout_swaps_days(client: TestClient) -> None:
    t = _templates(client)
    moved = client.patch(f"/api/workout-templates/{t['Upper A']['id']}", json={"weekday": 1}).json()
    assert moved["weekday"] == 1
    t = _templates(client)
    assert t["Lower A"]["weekday"] == 0  # swapped into Monday


def test_unschedule_and_rest_day(client: TestClient) -> None:
    t = _templates(client)
    client.patch(f"/api/workout-templates/{t['Upper A']['id']}", json={"unschedule": True})
    dashboard = client.get("/api/dashboard", params={"date": "2026-10-19"}).json()
    assert dashboard["today"] is None
    assert any(c["name"] == "Upper A" for c in dashboard["templates"])


def test_build_new_workout_from_library(client: TestClient) -> None:
    created = client.post("/api/workout-templates", json={"name": "Push Day", "weekday": 6})
    assert created.status_code == 201
    template = created.json()
    for exercise_id in ("EX0005", "EX0300", "EX0213"):
        r = client.post(f"/api/workout-templates/{template['id']}/exercises", json={"exercise_id": exercise_id})
        assert r.status_code == 201
    template = r.json()
    incline, dip, plank = template["exercises"]
    assert (incline["target_sets"], incline["target_rep_min"], incline["target_rep_max"]) == (3, 8, 12)
    assert dip["target_text"] == "10-15"
    assert plank["target_text"] == "30-45 sec"

    reordered = client.post(f"/api/workout-templates/{template['id']}/reorder",
                            json={"template_exercise_ids": [plank["id"], incline["id"], dip["id"]]}).json()
    assert [e["exercise"]["id"] for e in reordered["exercises"]] == ["EX0213", "EX0005", "EX0300"]

    edited = client.patch(f"/api/workout-templates/{template['id']}/exercises/{incline['id']}",
                          json={"target_rep_min": 6, "target_rep_max": 8, "target_sets": 4}).json()
    inc = next(e for e in edited["exercises"] if e["id"] == incline["id"])
    assert (inc["target_text"], inc["target_sets"]) == ("6-8", 4)

    bad = client.patch(f"/api/workout-templates/{template['id']}/exercises/{incline['id']}",
                       json={"target_rep_min": 10, "target_rep_max": 8})
    assert bad.status_code == 422

    sunday = client.get("/api/dashboard", params={"date": "2026-10-25"}).json()
    assert sunday["today"]["name"] == "Push Day"


def test_duplicate_template_name_rejected(client: TestClient) -> None:
    assert client.post("/api/workout-templates", json={"name": "upper a"}).status_code == 409


def test_copy_template(client: TestClient) -> None:
    source = _templates(client)["Upper A"]
    copy = client.post("/api/workout-templates", json={"name": "Upper A (hotel)", "copy_from_template_id": source["id"]}).json()
    assert [e["exercise"]["id"] for e in copy["exercises"]] == [e["exercise"]["id"] for e in source["exercises"]]
    assert copy["weekday"] is None


def test_exercise_library_filters_and_custom_exercise(client: TestClient) -> None:
    chest = client.get("/api/exercises", params={"muscle": "Chest"}).json()
    assert {e["id"] for e in chest} == {"EX0001", "EX0005", "EX0021", "EX0300"}
    triceps = client.get("/api/exercises", params={"muscle": "Triceps"}).json()
    assert [e["id"] for e in triceps] == ["EX0300"]
    search = client.get("/api/exercises", params={"search": "smith"}).json()
    assert [e["id"] for e in search] == ["EX0139"]
    bench = client.get("/api/exercises/EX0001").json()
    assert bench["scheduled_in"] == ["Upper A"]
    assert bench["weight_options"][:3] == [5, 10, 15]

    created = client.post("/api/exercises", json={"name": "Band pull-apart", "primary_muscle_group": "Shoulders",
                                                  "tracking_type": "bodyweight", "load_type": "bodyweight"})
    assert created.status_code == 201
    assert created.json()["id"] == "CX0001"
    assert client.post("/api/exercises", json={"name": "band pull-apart"}).status_code == 409

    disabled = client.patch("/api/exercises/EX0300", json={"enabled": False}).json()
    assert disabled["enabled"] is False
    ids = {e["id"] for e in client.get("/api/exercises").json()}
    assert "EX0300" not in ids
    ids_all = {e["id"] for e in client.get("/api/exercises", params={"include_disabled": True}).json()}
    assert "EX0300" in ids_all


def test_image_upload_and_placeholder(client: TestClient) -> None:
    from tests.conftest import png_bytes

    assert client.get("/api/exercises/EX0300").json()["image_url"] is None
    r = client.post("/api/exercises/EX0300/image", files={"file": ("dip.png", png_bytes("blue"), "image/png")})
    assert r.status_code == 200
    assert r.json()["image_url"].startswith("/media/exercise-images/ex0300-")
    bad = client.post("/api/exercises/EX0300/image", files={"file": ("x.png", b"not an image", "image/png")})
    assert bad.status_code == 422


def test_settings_program_week(client: TestClient) -> None:
    client.patch("/api/settings", json={"program_start_date": "2026-10-05"})
    dashboard = client.get("/api/dashboard", params={"date": "2026-10-19"}).json()
    assert dashboard["program_week"] == 3
    bench = dashboard["today"]["exercises"][0]
    assert bench["planned_sets"] == 3  # past the ramp-in weeks
