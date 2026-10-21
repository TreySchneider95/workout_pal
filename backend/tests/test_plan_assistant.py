import copy
import json

import pytest
from fastapi.testclient import TestClient

from app import config
from app.services.plan_exchange import DocumentError, read_document
from tests.conftest import ABBY
from tests.test_sessions import MONDAY, _complete_all, _start

AS_ABBY = {"X-Profile-Id": str(ABBY)}


def _export(client: TestClient, headers: dict | None = None) -> dict:
    return client.get("/api/plan-assistant/export", headers=headers).json()


def _reply(doc: dict) -> str:
    """What a chat AI typically sends back."""
    return f"Here's your updated plan!\n\n```json\n{json.dumps(doc, indent=2)}\n```\n\nLet me know how it goes."


def _workout(doc: dict, name: str) -> dict:
    return next(w for w in doc["workouts"] if w["name"] == name)


# --------------------------------------------------------------------------- prompt


def test_prompt_has_request_plan_library_and_format(client: TestClient) -> None:
    prompt = client.post("/api/plan-assistant/prompt", json={"request": "Add more core work"}).json()["prompt"]
    assert "Add more core work" in prompt
    assert "helping Trey" in prompt
    assert '"name": "Upper A"' in prompt  # current plan, already in the document format
    assert '"exercise_id": "EX0001"' in prompt
    assert "EX0300 | Chest; Triceps dip" in prompt  # library exercise not in the plan
    assert "lb per dumbbell" in prompt
    assert "pairs of 5, 10, 15" in prompt  # the dumbbells that exist
    assert "workout-pal-plan/v1" in prompt
    assert "COMPLETE plan" in prompt


def test_prompt_shows_recent_performance(client: TestClient) -> None:
    _complete_all(client, _start(client), reps=9)
    prompt = client.post("/api/plan-assistant/prompt", json={"request": "Heavier please"}).json()["prompt"]
    assert "EX0001 Flat dumbbell bench press: 2026-10-19 20 lb × 9, 9 (target 8-10)" in prompt


def test_prompt_for_profile_without_plan(client: TestClient) -> None:
    prompt = client.post("/api/plan-assistant/prompt", json={"request": "Build me a 3-day plan"},
                         headers=AS_ABBY).json()["prompt"]
    assert "helping Abby" in prompt
    assert "no plan yet" in prompt
    assert '"workouts": []' in prompt
    assert "Most recent performance" not in prompt


# --------------------------------------------------------------------------- reading the reply


def test_read_document_finds_json_in_chatty_reply() -> None:
    doc = {"workouts": [{"name": "A", "day": "Monday", "exercises": []}]}
    assert read_document(_reply(doc)).workouts[0].name == "A"
    assert read_document(json.dumps(doc)).workouts[0].name == "A"  # bare JSON
    smart = json.dumps(doc).replace('"', "“", 1)
    assert read_document(smart).workouts[0].name == "A"


@pytest.mark.parametrize(("text", "message"), [
    ("Sure! What equipment do you have?", "Couldn't find a JSON plan"),
    ('```json\n{"workouts": [\n```', "cut off"),
    ('{"workouts": [}', "malformed"),
    ('{"workouts": [{"name": "A", "exercises": [{"exercise_id": "EX0001", "sets": 0, "reps_or_duration": "8"}]}]}',
     "workout 'A' › exercise #1 (EX0001) › sets"),
])
def test_read_document_explains_problems(text: str, message: str) -> None:
    with pytest.raises(DocumentError) as exc:
        read_document(text)
    assert message in exc.value.errors[0]


# --------------------------------------------------------------------------- preview


def test_exported_plan_previews_as_unchanged(client: TestClient) -> None:
    preview = client.post("/api/plan-assistant/preview", json={"document": json.dumps(_export(client))}).json()
    assert preview["ok"], preview["errors"]
    assert {w["status"] for w in preview["workouts"]} == {"unchanged"}
    assert len(preview["workouts"]) == 4


def test_preview_lists_errors_and_warnings(client: TestClient) -> None:
    doc = _export(client)
    upper = _workout(doc, "Upper A")
    upper["exercises"][0]["weight"] = 22  # no 22 lb dumbbells
    upper["exercises"][1]["exercise_name"] = "Barbell back squat"  # doesn't match EX0021
    upper["exercises"].append({"exercise_id": "EX9999", "exercise_name": "Made up", "sets": 3,
                               "reps_or_duration": "10"})
    _workout(doc, "Lower A")["day"] = "Monday"
    _workout(doc, "Cardio Mobility")["exercises"][0]["reps_or_duration"] = "12"
    _workout(doc, "Upper B")["exercises"][0]["reps_or_duration"] = "lots"

    preview = client.post("/api/plan-assistant/preview", json={"document": _reply(doc)}).json()
    assert not preview["ok"]
    errors = "\n".join(preview["errors"])
    assert "EX9999 isn't in the exercise library" in errors
    assert "Monday has two workouts: 'Upper A' and 'Lower A'" in errors
    assert "cardio needs a duration" in errors
    assert "can't read reps_or_duration 'lots'" in errors
    warnings = "\n".join(preview["warnings"])
    assert "no 22 lb dumbbells; using 20 lb" in warnings
    assert "not 'Barbell back squat'" in warnings
    # Applying an invalid document is refused and changes nothing.
    response = client.post("/api/plan-assistant/apply", json={"document": _reply(doc)})
    assert response.status_code == 422
    assert _export(client) == _export(client) and len(_export(client)["workouts"]) == 4


def test_empty_plan_is_rejected(client: TestClient) -> None:
    preview = client.post("/api/plan-assistant/preview", json={"document": '{"workouts": []}'}).json()
    assert not preview["ok"]
    assert "delete the whole plan" in preview["errors"][0]


# --------------------------------------------------------------------------- applying


def _changed_plan(client: TestClient) -> dict:
    doc = _export(client)
    doc["summary"] = "Heavier bench, dips added, Upper B dropped, cardio on Sunday."
    upper = _workout(doc, "Upper A")
    upper["exercises"][0]["weight"] = 25
    upper["exercises"].append({"exercise_id": "ex0300", "exercise_name": "Chest; Triceps dip", "sets": 3,
                               "reps_or_duration": "6-10", "weight": 0, "rest_seconds": 90})
    doc["workouts"] = [w for w in doc["workouts"] if w["name"] != "Upper B"]
    _workout(doc, "Cardio Mobility")["day"] = "sun"
    doc["workouts"].append({"name": "Arms", "day": None, "exercises": [
        {"exercise_id": "EX0005", "sets": 2, "reps_or_duration": "10-12", "weight": 15}]})
    return doc


def test_preview_describes_changes(client: TestClient) -> None:
    preview = client.post("/api/plan-assistant/preview", json={"document": _reply(_changed_plan(client))}).json()
    assert preview["ok"], preview["errors"]
    assert preview["summary"].startswith("Heavier bench")
    by_name = {w["name"]: w for w in preview["workouts"]}
    upper = by_name["Upper A"]
    assert upper["status"] == "changed"
    assert [(e["exercise_id"], e["status"]) for e in upper["exercises"]] == [
        ("EX0001", "changed"), ("EX0021", "unchanged"), ("EX0300", "added")]
    assert upper["exercises"][0]["changes"] == ["weight 20 → 25 lb"]
    assert by_name["Upper B"]["status"] == "removed"
    assert by_name["Arms"]["status"] == "added"
    assert by_name["Cardio Mobility"]["notes"] == ["Moved from Saturday to Sunday"]
    assert by_name["Lower A"]["status"] == "unchanged"


def test_apply_replaces_plan_and_keeps_history(client: TestClient) -> None:
    before = {t["name"]: t for t in client.get("/api/workout-templates").json()}
    session = _start(client, name="Upper B")
    _complete_all(client, session, reps=10)

    revision = client.post("/api/plan-assistant/apply", json={"document": _reply(_changed_plan(client))})
    assert revision.status_code == 200, revision.text
    assert revision.json()["can_undo"]

    after = {t["name"]: t for t in client.get("/api/workout-templates").json()}
    assert set(after) == {"Upper A", "Lower A", "Cardio Mobility", "Arms"}
    assert after["Upper A"]["id"] == before["Upper A"]["id"]  # updated in place
    assert [te["exercise"]["id"] for te in after["Upper A"]["exercises"]] == ["EX0001", "EX0021", "EX0300"]
    assert after["Upper A"]["exercises"][0]["suggested_weight"] == 25
    assert after["Cardio Mobility"]["weekday"] == 6
    assert after["Arms"]["weekday"] is None
    # Upper B is gone but its recorded workout isn't.
    recorded = client.get(f"/api/workout-sessions/{session['id']}").json()
    assert recorded["name"] == "Upper B" and recorded["workout_template_id"] is None
    assert client.get("/api/history").json()["total"] == 1


def test_changed_weight_wins_over_history(client: TestClient) -> None:
    _complete_all(client, _start(client), reps=9)  # 20 lb last time
    client.post("/api/plan-assistant/apply", json={"document": _reply(_changed_plan(client))})
    session = _start(client, day="2026-10-26")
    bench, fly, dip = session["exercises"]
    assert bench["suggestion_action"] == "plan"
    assert bench["sets"][0]["weight"] == 25
    assert fly["suggestion_action"] != "plan"  # untouched weight: history still drives it


def test_skipped_exercises_survive(client: TestClient) -> None:
    upper = client.get("/api/workout-templates").json()[0]
    te = upper["exercises"][1]
    client.patch(f"/api/workout-templates/{upper['id']}/exercises/{te['id']}", json={"skipped": True})
    doc = _export(client)
    assert _workout(doc, "Upper A")["exercises"][1]["skipped"] is True
    client.post("/api/plan-assistant/apply", json={"document": json.dumps(doc)})
    again = client.get(f"/api/workout-templates/{upper['id']}").json()
    assert [e["skipped"] for e in again["exercises"]] == [False, True]


def test_undo_and_redo(client: TestClient) -> None:
    original = _export(client)
    first = client.post("/api/plan-assistant/apply", json={"document": _reply(_changed_plan(client))}).json()
    changed = _export(client)

    undone = client.post(f"/api/plan-assistant/revisions/{first['id']}/undo")
    assert undone.status_code == 200, undone.text
    assert undone.json()["source"] == "undo"
    assert _strip(_export(client)) == _strip(original)

    revisions = client.get("/api/plan-assistant/revisions").json()
    assert [(r["source"], r["can_undo"], r["undone_at"] is not None) for r in revisions] == [
        ("undo", True, False), ("document", False, True)]
    # Only the latest change can be undone; undoing the undo puts the change back.
    assert client.post(f"/api/plan-assistant/revisions/{first['id']}/undo").status_code == 409
    client.post(f"/api/plan-assistant/revisions/{revisions[0]['id']}/undo")
    assert _strip(_export(client)) == _strip(changed)


def _strip(doc: dict) -> list:
    """Compare plans by content, ignoring workout order."""
    return sorted((json.dumps(w, sort_keys=True) for w in doc["workouts"]))


def test_first_plan_for_abby_and_undo_to_empty(client: TestClient) -> None:
    doc = copy.deepcopy(_export(client))
    doc["workouts"] = doc["workouts"][:2]
    revision = client.post("/api/plan-assistant/apply", json={"document": _reply(doc)}, headers=AS_ABBY).json()
    assert [t["name"] for t in client.get("/api/workout-templates", headers=AS_ABBY).json()] == ["Upper A", "Lower A"]
    assert len(client.get("/api/workout-templates").json()) == 4  # Trey's plan untouched
    assert client.get("/api/plan-assistant/revisions").json() == []
    client.post(f"/api/plan-assistant/revisions/{revision['id']}/undo", headers=AS_ABBY)
    assert client.get("/api/workout-templates", headers=AS_ABBY).json() == []


# --------------------------------------------------------------------------- email


def test_profile_email(client: TestClient) -> None:
    assert client.patch("/api/profiles/1", json={"email": "not-an-email"}).status_code == 422
    assert client.patch("/api/profiles/1", json={"email": " trey@example.com "}).json()["email"] == "trey@example.com"
    assert client.get("/api/plan-assistant/status").json() == {"email_enabled": False, "email": "trey@example.com"}
    assert client.patch("/api/profiles/1", json={"email": ""}).json()["email"] is None


def test_email_needs_address_and_server(client: TestClient) -> None:
    body = {"request": "Shorter workouts"}
    assert "Add an email address" in client.post("/api/plan-assistant/email", json=body).json()["detail"]
    client.patch("/api/profiles/1", json={"email": "trey@example.com"})
    response = client.post("/api/plan-assistant/email", json=body)
    assert response.status_code == 502
    assert "isn't set up" in response.json()["detail"]


def test_email_sends_prompt(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    sent = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            sent.append(("connect", host, port))

        def __enter__(self):  # noqa: ANN204
            return self

        def __exit__(self, *exc: object) -> None:
            pass

        def starttls(self, context: object) -> None:
            sent.append(("starttls",))

        def login(self, user: str, password: str) -> None:
            sent.append(("login", user, password))

        def send_message(self, message: object) -> None:
            sent.append(("message", message))

    for key, value in {"SMTP_HOST": "smtp.example.com", "SMTP_USERNAME": "pal@example.com",
                       "SMTP_PASSWORD": "app-password", "APP_URL": "http://raspberrypi.local:8080"}.items():
        monkeypatch.setenv(f"WORKOUT_{key}", value)
    config.get_settings.cache_clear()
    monkeypatch.setattr("app.services.mailer.smtplib.SMTP", FakeSMTP)
    client.patch("/api/profiles/1", json={"email": "trey@example.com"})

    response = client.post("/api/plan-assistant/email", json={"request": "Shorter workouts"}, params={"date": MONDAY})
    assert response.json() == {"sent_to": "trey@example.com"}
    assert sent[:3] == [("connect", "smtp.example.com", 587), ("starttls",), ("login", "pal@example.com", "app-password")]
    message = sent[3][1]
    assert message["To"] == "trey@example.com"
    assert message["From"] == "pal@example.com"
    body = message.get_body(("plain",)).get_content()
    assert "Shorter workouts" in body
    assert "http://raspberrypi.local:8080/schedule/assistant" in body
    assert "workout-pal-plan/v1" in body
    attachment = next(message.iter_attachments())
    assert attachment.get_filename() == "workout-pal-prompt.txt"
    assert "EX0001" in attachment.get_content()
