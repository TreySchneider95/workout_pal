from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Exercise
from tests.conftest import png_bytes
from tests.test_plan_assistant import AS_ABBY


def _items(client: TestClient, **params: str) -> dict[str, dict]:
    response = client.get("/api/image-prompts", params=params)
    assert response.status_code == 200, response.text
    return {i["exercise"]["id"]: i for i in response.json()}


def test_lists_plan_exercises_in_plan_order(client: TestClient, seeded: Session) -> None:
    seeded.get(Exercise, "EX0139").image_path = None
    seeded.commit()
    items = _items(client)
    assert list(items) == ["EX0001", "EX0021", "EX0139", "EX0213", "EX0005", "EX0263"]
    assert [i for i, item in items.items() if not item["has_image"]] == ["EX0139"]
    assert items["EX0139"]["workouts"] == ["Lower A (Tue)"]
    assert "EX0300" not in items  # in the library but not the plan
    assert client.get("/api/image-prompts", headers=AS_ABBY).json() == []  # Abby has no plan


def test_prompt_describes_one_picture_in_the_house_style(client: TestClient) -> None:
    items = _items(client)
    squat = items["EX0139"]["prompt"]
    assert squat.startswith('Create ONE image: an exercise instruction infographic for "Smith squat"')
    assert "Make exactly one\npicture" in squat
    assert "Smith machine (a barbell that slides on fixed vertical rails)" in squat
    assert "Main muscle group: Quadriceps" in squat
    assert "Their plan: 3 sets of 8-10 reps" in squat
    assert "Notes from their plan (use only what describes the movement): Assess bar." in squat
    for part in ('"START POSITION"', '"END POSITION"', '"MUSCLES WORKED"', '"KEY FORM TIPS"', '"COMMON MISTAKES"',
                 "PRO TIPS", "4:5", "fit adult man"):
        assert part in squat

    fly = items["EX0021"]["prompt"]
    assert "with a single-grip cable handle" in fly
    assert "one side at a time" in fly
    assert "Their plan: 2 sets of 12 reps per side" in fly

    plank = items["EX0213"]["prompt"]
    assert '"HOLD POSITION"' in plank and "3 sets of 20-40 sec" in plank
    walk = items["EX0263"]["prompt"]
    assert '"IN MOTION"' in walk and "Their plan: 30-40 min" in walk

    assert "fit adult woman" in _items(client, person="woman")["EX0139"]["prompt"]
    assert client.get("/api/image-prompts", params={"person": "dog"}).status_code == 422


def test_uploaded_picture_marks_it_done(client: TestClient, seeded: Session) -> None:
    seeded.get(Exercise, "EX0139").image_path = None
    seeded.commit()
    client.post("/api/exercises/EX0139/image", files={"file": ("squat.png", png_bytes(), "image/png")})
    assert _items(client)["EX0139"]["has_image"]
