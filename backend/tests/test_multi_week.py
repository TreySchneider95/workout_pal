"""Multi-week plans: workouts that run only in some weeks of a plan that repeats every N weeks."""

import json

from fastapi.testclient import TestClient

from tests.test_plan_assistant import _export, _reply, _workout

MONDAY = "2026-10-19"  # week 1 once the plan is restarted on this date


def _three_week_doc(client: TestClient) -> dict:
    """Trey's plan, with Upper A in weeks 1-2 and a lighter Upper A in week 3 on the same day."""
    doc = _export(client)
    doc["summary"] = "3-week block with a deload."
    doc["plan_weeks"] = 3
    upper = _workout(doc, "Upper A")
    upper["weeks"] = [1, 2]
    deload = json.loads(json.dumps(upper))
    deload.update(name="Upper A · Deload", weeks=[3])
    for e in deload["exercises"]:
        e["sets"] = 1
    doc["workouts"].append(deload)
    return doc


def _dashboard(client: TestClient, day: str) -> dict:
    return client.get("/api/dashboard", params={"date": day}).json()


def _apply(client: TestClient, doc: dict, restart: bool = True) -> dict:
    response = client.post("/api/plan-assistant/apply", params={"date": MONDAY},
                           json={"document": _reply(doc), "restart": restart})
    assert response.status_code == 200, response.text
    return response.json()


def test_preview_shows_weeks(client: TestClient) -> None:
    preview = client.post("/api/plan-assistant/preview", json={"document": _reply(_three_week_doc(client))}).json()
    assert preview["ok"], preview["errors"]
    assert (preview["plan_weeks"], preview["previous_plan_weeks"]) == (3, 1)
    by_name = {w["name"]: w for w in preview["workouts"]}
    assert by_name["Upper A"]["notes"] == ["Now weeks 1–2 (was every week)"]
    assert by_name["Upper A · Deload"]["status"] == "added"
    assert by_name["Upper A · Deload"]["weeks_text"] == "Week 3"
    assert by_name["Lower A"]["weeks_text"] == "Every week"
    assert by_name["Lower A"]["status"] == "unchanged"


def test_apply_schedules_by_week_and_repeats(client: TestClient) -> None:
    client.patch("/api/settings", json={"program_start_date": "2026-09-07"})  # training for a while
    _apply(client, _three_week_doc(client))
    settings = client.get("/api/settings").json()
    assert (settings["plan_weeks"], settings["plan_start_date"]) == (3, MONDAY)
    # Restarting the plan doesn't restart training (and with it the lighter ramp-in sets).
    assert settings["program_start_date"] == "2026-09-07"

    expected = {
        "2026-10-19": (1, "Upper A"),
        "2026-10-26": (2, "Upper A"),
        "2026-11-02": (3, "Upper A · Deload"),
        "2026-11-09": (1, "Upper A"),  # starts over after week 3
    }
    for day, (week, name) in expected.items():
        d = _dashboard(client, day)
        assert (d["plan_week"], d["plan_weeks"], d["today"]["name"]) == (week, 3, name), day
        # This week's workouts are listed first.
        assert d["templates"][0]["name"] == name
    # Tuesday's workout runs every week.
    assert _dashboard(client, "2026-11-03")["today"]["name"] == "Lower A"

    # Starting the deload records the plan's (lighter) prescription.
    deload = next(t for t in client.get("/api/workout-templates").json() if t["name"] == "Upper A · Deload")
    session = client.post("/api/workout-sessions",
                          json={"workout_template_id": deload["id"], "performed_on": "2026-11-02"}).json()
    assert [e["target_sets"] for e in session["exercises"]] == [1, 1]


def test_exported_multi_week_plan_round_trips(client: TestClient) -> None:
    _apply(client, _three_week_doc(client))
    doc = _export(client)
    assert doc["format"] == "workout-pal-plan/v2"
    assert doc["plan_weeks"] == 3
    assert _workout(doc, "Upper A")["weeks"] == [1, 2]
    assert _workout(doc, "Lower A")["weeks"] is None
    preview = client.post("/api/plan-assistant/preview", json={"document": json.dumps(doc)}).json()
    assert preview["ok"] and preview["warnings"] == []
    assert {w["status"] for w in preview["workouts"]} == {"unchanged"}


def test_undo_restores_weekly_plan_and_start_date(client: TestClient) -> None:
    client.patch("/api/settings", json={"plan_start_date": "2026-09-07"})
    revision = _apply(client, _three_week_doc(client))
    client.post(f"/api/plan-assistant/revisions/{revision['id']}/undo")
    settings = client.get("/api/settings").json()
    assert (settings["plan_weeks"], settings["plan_start_date"]) == (1, "2026-09-07")
    assert [t["name"] for t in client.get("/api/workout-templates").json()] == [
        "Upper A", "Lower A", "Upper B", "Cardio Mobility"]
    assert all(t["weeks"] is None for t in client.get("/api/workout-templates").json())


def test_apply_without_restart_keeps_program_week(client: TestClient) -> None:
    client.patch("/api/settings", json={"plan_start_date": "2026-10-05"})
    _apply(client, _three_week_doc(client), restart=False)
    d = _dashboard(client, MONDAY)
    assert d["plan_week"] == 3
    assert d["today"]["name"] == "Upper A · Deload"


def test_validation_of_weeks(client: TestClient) -> None:
    doc = _three_week_doc(client)
    _workout(doc, "Upper A · Deload")["weeks"] = "2-3"  # overlaps Upper A in week 2
    _workout(doc, "Lower A")["weeks"] = [4]
    preview = client.post("/api/plan-assistant/preview", json={"document": _reply(doc)}).json()
    assert not preview["ok"]
    assert any("some workouts are in week 4" in e for e in preview["errors"])
    assert "Monday has two workouts in week 2: 'Upper A' and 'Upper A · Deload'." in preview["errors"]

    doc = _three_week_doc(client)
    doc["plan_weeks"] = 4
    _workout(doc, "Upper A · Deload")["weeks"] = "weeks 3 and 4"
    preview = client.post("/api/plan-assistant/preview", json={"document": _reply(doc)}).json()
    assert preview["ok"], preview["errors"]
    assert _workout(preview, "Upper A · Deload")["weeks"] == [3, 4]

    doc = _export(client)
    doc["plan_weeks"] = 2
    preview = client.post("/api/plan-assistant/preview", json={"document": _reply(doc)}).json()
    assert any("every workout runs every week" in w for w in preview["warnings"])

    doc = _export(client)
    doc["plan_weeks"] = 2
    for w in doc["workouts"]:
        w["weeks"] = [1]
    preview = client.post("/api/plan-assistant/preview", json={"document": _reply(doc)}).json()
    assert "Week 2 has no scheduled workouts (a rest week)." in preview["warnings"]


def test_v1_documents_still_work(client: TestClient) -> None:
    doc = _export(client)
    doc["format"] = "workout-pal-plan/v1"
    del doc["plan_weeks"]
    for w in doc["workouts"]:
        del w["weeks"]
    preview = client.post("/api/plan-assistant/preview", json={"document": json.dumps(doc)}).json()
    assert preview["ok"] and preview["warnings"] == [] and preview["plan_weeks"] == 1


def test_prompt_explains_multi_week_plans(client: TestClient) -> None:
    prompt = client.post("/api/plan-assistant/prompt", json={"request": "Give me a 6-week plan"}).json()["prompt"]
    assert "a weekly plan (the same workouts every week)" in prompt
    assert "multi-week program" in prompt
    assert '"plan_weeks": 1' in prompt  # current plan
    assert '"weeks": [\n' in prompt  # example

    _apply(client, _three_week_doc(client))
    prompt = client.post("/api/plan-assistant/prompt", params={"date": "2026-10-26"},
                         json={"request": "Harder"}).json()["prompt"]
    assert "a 3-week plan; this is week 2 of 3" in prompt


# --------------------------------------------------------------------------- editing by hand


def _templates(client: TestClient) -> dict[str, dict]:
    return {t["name"]: t for t in client.get("/api/workout-templates").json()}


def test_week_specific_workouts_by_hand(client: TestClient) -> None:
    client.patch("/api/settings", json={"plan_weeks": 2, "plan_start_date": MONDAY})
    t = _templates(client)
    # Upper A only in week 1; a new workout takes Monday in week 2.
    r = client.patch(f"/api/workout-templates/{t['Upper A']['id']}", json={"weeks": [1]})
    assert r.json()["weeks"] == [1] and r.json()["weeks_text"] == "Week 1"
    created = client.post("/api/workout-templates", json={
        "name": "Upper A2", "weekday": 0, "weeks": [2], "copy_from_template_id": t["Upper A"]["id"]})
    assert created.status_code == 201
    assert _templates(client)["Upper A"]["weekday"] == 0  # not displaced: different weeks
    assert _dashboard(client, "2026-10-26")["today"]["name"] == "Upper A2"

    # Making Upper A2 run every week would double-book Monday in week 1.
    clash = client.patch(f"/api/workout-templates/{created.json()['id']}", json={"weeks": None})
    assert clash.status_code == 409 and "Upper A" in clash.json()["detail"]
    # Weeks past the end of the plan are refused; all weeks means every week.
    assert client.patch(f"/api/workout-templates/{t['Lower A']['id']}", json={"weeks": [3]}).status_code == 422
    assert client.patch(f"/api/workout-templates/{t['Lower A']['id']}", json={"weeks": [1, 2]}).json()["weeks"] is None

    # Moving an every-week workout onto Monday swaps out both of Monday's workouts.
    client.patch(f"/api/workout-templates/{t['Lower A']['id']}", json={"weekday": 0})
    t = _templates(client)
    assert (t["Lower A"]["weekday"], t["Upper A"]["weekday"], t["Upper A2"]["weekday"]) == (0, 1, 1)

    # Shortening the plan drops week 2: Upper A runs every week, Upper A2 is unscheduled.
    client.patch("/api/settings", json={"plan_weeks": 1})
    t = _templates(client)
    assert (t["Upper A"]["weeks"], t["Upper A"]["weekday"]) == (None, 1)
    assert (t["Upper A2"]["weeks"], t["Upper A2"]["weekday"]) == (None, None)


def test_analytics_counts_planned_days_per_week(client: TestClient) -> None:
    doc = _three_week_doc(client)
    _workout(doc, "Lower A")["weeks"] = [1, 2]  # week 3 has only the deload + Upper B + cardio
    _apply(client, doc)
    week3 = client.get("/api/analytics/summary", params={"date": "2026-11-02"}).json()
    week1 = client.get("/api/analytics/summary", params={"date": MONDAY}).json()
    assert (week1["planned_this_week"], week3["planned_this_week"]) == (4, 3)
