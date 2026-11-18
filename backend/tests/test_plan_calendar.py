"""Plan weeks vs. training weeks, and how schedule changes treat the workouts already on a day."""

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import WorkoutTemplate
from app.services.importer import run_import
from app.services.plan import get_app_settings
from app.services.plan_exchange import _example_document
from tests.conftest import TREY
from tests.test_multi_week import MONDAY, _apply, _dashboard, _three_week_doc
from tests.test_plan_assistant import _export, _reply, _workout


def _settings(client: TestClient) -> dict:
    return client.get("/api/settings").json()


def _templates(client: TestClient) -> dict[str, dict]:
    return {t["name"]: t for t in client.get("/api/workout-templates").json()}


def _sets(client: TestClient, template: str, day: str) -> list[int]:
    """Set counts a session of `template` on `day` would get (the session is thrown away)."""
    t = _templates(client)[template]
    session = client.post("/api/workout-sessions", json={"workout_template_id": t["id"], "performed_on": day}).json()
    client.delete(f"/api/workout-sessions/{session['id']}")
    return [e["target_sets"] for e in session["exercises"]]


# --------------------------------------------------------------------------- plan start vs. training start


def test_restarting_the_plan_keeps_the_ramp_in_finished(client: TestClient) -> None:
    client.patch("/api/settings", json={"program_start_date": "2026-09-07"})
    full = _sets(client, "Lower A", "2026-10-20")
    _apply(client, _three_week_doc(client))  # restarts the plan on MONDAY
    assert _sets(client, "Lower A", "2026-10-20") == full
    # "Make week 2 this week" moves only the plan.
    client.patch("/api/settings", json={"plan_start_date": "2026-10-12"})
    assert _settings(client)["program_start_date"] == "2026-09-07"
    d = _dashboard(client, MONDAY)
    assert (d["plan_week"], d["program_week"]) == (2, 7)
    assert _sets(client, "Lower A", "2026-10-20") == full


def test_weekend_restart_starts_week_one_on_monday(client: TestClient) -> None:
    response = client.post("/api/plan-assistant/apply", params={"date": "2026-10-25"},  # a Sunday
                           json={"document": _reply(_three_week_doc(client)), "restart": True})
    assert response.status_code == 200
    assert _settings(client)["plan_start_date"] == "2026-10-26"
    assert _dashboard(client, "2026-10-25")["plan_week"] == 1
    assert _dashboard(client, "2026-10-26")["plan_week"] == 1
    assert _dashboard(client, "2026-11-02")["plan_week"] == 2


def test_training_weeks_count_seven_days_from_the_first_workout(client: TestClient) -> None:
    first = _templates(client)["Upper A"]
    client.post("/api/workout-sessions", json={"workout_template_id": first["id"], "performed_on": "2026-11-01"})
    settings = _settings(client)
    assert (settings["program_start_date"], settings["plan_start_date"]) == ("2026-11-01", "2026-11-02")
    assert _dashboard(client, "2026-11-07")["program_week"] == 1
    assert _dashboard(client, "2026-11-09")["program_week"] == 2  # still a ramp-in week


def test_changing_plan_length_keeps_todays_week(client: TestClient) -> None:
    _apply(client, _three_week_doc(client))
    d = _dashboard(client, "2026-11-09")
    assert (d["plan_week"], d["today"]["name"]) == (1, "Upper A")
    client.patch("/api/settings", params={"date": "2026-11-09"}, json={"plan_weeks": 4})
    d = _dashboard(client, "2026-11-09")
    assert (d["plan_week"], d["plan_weeks"], d["today"]["name"]) == (1, 4, "Upper A")

    # Back to 3 weeks, then shorten to 2 during week 3 (11-02): week 3 is gone, so it's week 1.
    client.patch("/api/settings", json={"plan_weeks": 3, "plan_start_date": MONDAY})
    assert _dashboard(client, "2026-11-02")["plan_week"] == 3
    client.patch("/api/settings", params={"date": "2026-11-02"}, json={"plan_weeks": 2})
    d = _dashboard(client, "2026-11-02")
    assert (d["plan_week"], d["today"]["name"]) == (1, "Upper A")


def test_undoing_an_undo_brings_back_the_restart(client: TestClient) -> None:
    client.patch("/api/settings", json={"plan_start_date": "2026-09-07"})
    revision = _apply(client, _three_week_doc(client))
    undo = client.post(f"/api/plan-assistant/revisions/{revision['id']}/undo").json()
    assert _settings(client)["plan_start_date"] == "2026-09-07"
    client.post(f"/api/plan-assistant/revisions/{undo['id']}/undo")
    settings = _settings(client)
    assert (settings["plan_weeks"], settings["plan_start_date"]) == (3, MONDAY)
    assert _dashboard(client, MONDAY)["today"]["name"] == "Upper A"


# --------------------------------------------------------------------------- stats keep their history


def _complete(client: TestClient, template: str, day: str) -> None:
    t = _templates(client)[template]
    session = client.post("/api/workout-sessions", json={"workout_template_id": t["id"], "performed_on": day}).json()
    assert client.post(f"/api/workout-sessions/{session['id']}/complete", json={}).status_code == 200


def test_moving_the_plan_week_doesnt_rewrite_past_weeks(client: TestClient) -> None:
    # A 2-week plan: Upper A on Monday in week 1, Upper B on Thursday in week 2, nothing else.
    doc = _export(client)
    doc["plan_weeks"] = 2
    for w in doc["workouts"]:
        w["day"], w["weeks"] = None, None
    _workout(doc, "Upper A").update(day="Monday", weeks=[1])
    _workout(doc, "Upper B").update(day="Thursday", weeks=[2])
    _apply(client, doc)
    for name, day in [("Upper A", "2026-10-19"), ("Upper B", "2026-10-29"),
                      ("Upper A", "2026-11-02"), ("Upper B", "2026-11-12")]:
        _complete(client, name, day)

    def summary() -> dict:
        return client.get("/api/analytics/summary", params={"date": "2026-11-16"}).json()

    before = summary()
    # Today (Monday 11-16, week 1) isn't done yet.
    assert (before["current_streak_weeks"], before["consistency_percent"]) == (4, 80)
    # Make this week week 2: past weeks stay as they were; this week now has Thursday planned.
    client.patch("/api/settings", json={"plan_start_date": "2026-11-09"})
    after = summary()
    assert (after["current_streak_weeks"], after["consistency_percent"]) == (4, 100)
    planned = [d["date"] for d in after["calendar"] if d["planned"] and d["date"] >= "2026-10-19"]
    assert planned == ["2026-10-19", "2026-10-29", "2026-11-02", "2026-11-12", "2026-11-19"]


# --------------------------------------------------------------------------- making room on a day


def test_week_specific_workout_takes_the_day_only_in_its_weeks(client: TestClient) -> None:
    client.patch("/api/settings", json={"plan_weeks": 3, "plan_start_date": MONDAY})
    upper = _templates(client)["Upper A"]
    created = client.post("/api/workout-templates", json={
        "name": "Upper A · Deload", "weekday": 0, "weeks": [3], "copy_from_template_id": upper["id"]})
    assert created.status_code == 201
    assert created.json()["schedule_notes"] == ["Upper A now runs on Monday in weeks 1–2 only."]
    t = _templates(client)
    assert (t["Upper A"]["weekday"], t["Upper A"]["weeks"]) == (0, [1, 2])
    names = [_dashboard(client, day)["today"]["name"] for day in ("2026-10-19", "2026-10-26", "2026-11-02")]
    assert names == ["Upper A", "Upper A", "Upper A · Deload"]


def test_moving_a_workout_reports_what_happened(client: TestClient) -> None:
    t = _templates(client)
    swapped = client.patch(f"/api/workout-templates/{t['Upper A']['id']}", json={"weekday": 1}).json()
    assert swapped["schedule_notes"] == ["Lower A moved to Monday."]
    client.patch(f"/api/workout-templates/{t['Upper A']['id']}", json={"weekday": 0})  # back again

    # 2 weeks: Upper A on Monday in week 1, Upper A2 on Monday in week 2.
    client.patch("/api/settings", json={"plan_weeks": 2, "plan_start_date": MONDAY})
    client.patch(f"/api/workout-templates/{t['Upper A']['id']}", json={"weeks": [1]})
    client.post("/api/workout-templates", json={"name": "Upper A2", "weekday": 0, "weeks": [2]})
    # Lower A (every Tuesday) can't swap onto Monday: week 2 there is taken. It keeps week 2.
    moved = client.patch(f"/api/workout-templates/{t['Upper A']['id']}", json={"weekday": 1}).json()
    assert moved["schedule_notes"] == ["Lower A now runs on Tuesday in week 2 only."]
    t = _templates(client)
    assert (t["Lower A"]["weekday"], t["Lower A"]["weeks"]) == (1, [2])
    assert (t["Upper A"]["weekday"], t["Upper A"]["weeks"]) == (1, [1])


def test_changing_weeks_and_day_together(client: TestClient) -> None:
    client.patch("/api/settings", json={"plan_weeks": 2, "plan_start_date": MONDAY})
    t = _templates(client)
    client.patch(f"/api/workout-templates/{t['Upper A']['id']}", json={"weeks": [1]})
    client.post("/api/workout-templates", json={"name": "Upper A2", "weekday": 0, "weeks": [2]})
    # Every week would clash with Upper A2 on Monday, but Upper A is leaving Monday.
    r = client.patch(f"/api/workout-templates/{t['Upper A']['id']}", json={"weeks": None, "weekday": 5})
    assert r.status_code == 200, r.text
    assert (r.json()["weekday"], r.json()["weeks"]) == (5, None)


# --------------------------------------------------------------------------- plan documents


def test_empty_or_out_of_range_weeks_are_errors(client: TestClient) -> None:
    doc = _three_week_doc(client)
    _workout(doc, "Upper B")["weeks"] = []
    preview = client.post("/api/plan-assistant/preview", json={"document": _reply(doc)}).json()
    assert not preview["ok"]
    assert any('"weeks": []' in e for e in preview["errors"])

    _workout(doc, "Upper B")["weeks"] = "14-16"
    preview = client.post("/api/plan-assistant/preview", json={"document": _reply(doc)}).json()
    assert not preview["ok"]


def test_prompt_example_keeps_the_deload_weight(client: TestClient) -> None:
    example = json.loads(_example_document())
    assert len({w["exercises"][0]["weight"] for w in example["workouts"]}) == 1
    prompt = client.post("/api/plan-assistant/prompt", json={"request": "Add a deload"}).json()["prompt"]
    assert "not a lower weight" in prompt


# --------------------------------------------------------------------------- CSV import


def test_reimporting_the_weekly_plan_runs_it_every_week(
    seeded: Session, library_csv: Path, plan_zip: Path, data_dir: Path,
) -> None:
    db = seeded
    get_app_settings(db, TREY).plan_weeks = 2
    upper = db.scalar(select(WorkoutTemplate).where(WorkoutTemplate.name == "Upper A"))
    upper.weeks = [1]
    db.commit()
    report = run_import(db, library_path=library_csv, plan_path=plan_zip, media_dir=data_dir / "media")
    db.expire_all()
    upper = db.scalar(select(WorkoutTemplate).where(WorkoutTemplate.name == "Upper A"))
    assert (upper.weekday, upper.weeks) == (0, None)
    assert any("Upper A" in w and "every week" in w for w in report.warnings)
