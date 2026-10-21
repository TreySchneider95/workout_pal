import io
import os
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from PIL import Image

# Point the app at a throwaway data dir before anything imports the settings.
_SESSION_TMP = Path(os.environ.setdefault("WORKOUT_DATA_DIR", "/tmp/workout-pal-tests-unused"))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app import config, db as db_module  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent
# Profiles created by the migrations; the seeded plan belongs to Trey.
TREY, ABBY = 1, 2
PROJECT_DIR = BACKEND_DIR.parent

LIBRARY_CSV = """﻿exercise_id,exercise_name,primary_muscle_group,equipment,attachment,tracking_type,track_per_side,notes
EX0001,Flat dumbbell bench press,Chest,Dumbbells + adjustable bench,,weight_reps,no,
EX0005,Incline dumbbell bench press,Chest,Dumbbells + adjustable bench,,weight_reps,no,
EX0021,Single-arm cable fly mid-height,Chest,Goimu WM1,Single-grip cable handle,weight_reps,yes,
EX0139,Smith squat,Quadriceps,RitFit PSR05 2.0 Smith machine,,weight_reps,no,
EX0213,Forearm plank,Core,Bodyweight,,reps_or_seconds,no,
EX0263,Treadmill brisk walking,Cardio,Treadmill,,time_distance_speed,no,
EX0300,Chest; Triceps dip,Chest; Triceps,Bodyweight,,reps,no,
"""

PLAN_CSV = """﻿week_day,session,order,exercise_id,exercise_name,sets_week_1_2,sets_week_3_plus,reps_or_duration,starting_weight,weight_unit,pulley_ratio,rest_seconds,notes,image_key,image_path
Monday,Upper A,1,EX0001,Flat dumbbell bench press,2,3,8-10,20,lb_per_dumbbell,,120,,ex0001.png,images/ex0001.png
Monday,Upper A,2,EX0021,Single-arm cable fly mid-height,2,2,12/side,10,lb_plates_loaded,2:1,75,Handle note.,ex0021.png,images/ex0021.png
Tuesday,Lower A,1,EX0139,Smith squat,2,3,8-10,20,lb_added_plates,,120,Assess bar.,ex0139.png,images/ex0139.png
Tuesday,Lower A,2,EX0213,Forearm plank,2,3,20-40 sec,0,bodyweight,,60,,ex0213.png,images/ex0213.png
Thursday,Upper B,1,EX0005,Incline dumbbell bench press,2,3,8-10,15,lb_per_dumbbell,,120,,ex0005.png,images/ex0005.png
Saturday,Cardio Mobility,1,EX0263,Treadmill brisk walking,1,1,30-40 min,0,bodyweight,,0,Easy pace.,ex0263.png,images/ex0263.png
"""


def png_bytes(color: str = "red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (40, 60), color).save(buf, "PNG")
    return buf.getvalue()


def make_plan_zip(path: Path, plan_csv: str = PLAN_CSV, skip_images: set[str] = frozenset()) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("home_gym_weekly_workout_plan_with_images.csv", plan_csv)
        for name in ["ex0001.png", "ex0005.png", "ex0021.png", "ex0139.png", "ex0213.png", "ex0263.png"]:
            if name not in skip_images:
                zf.writestr(f"images/{name}", png_bytes())
    return path


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    data = tmp_path / "data"
    monkeypatch.setenv("WORKOUT_DATA_DIR", str(data))
    config.get_settings.cache_clear()
    db_module.reset_engine()
    data.mkdir()
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")
    yield data
    db_module.reset_engine()
    config.get_settings.cache_clear()


@pytest.fixture
def db(data_dir: Path) -> Iterator[Session]:
    session = db_module.session_factory()()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def library_csv(tmp_path: Path) -> Path:
    path = tmp_path / "library.csv"
    path.write_text(LIBRARY_CSV, encoding="utf-8")
    return path


@pytest.fixture
def plan_zip(tmp_path: Path) -> Path:
    return make_plan_zip(tmp_path / "plan.zip")


@pytest.fixture
def seeded(db: Session, data_dir: Path, library_csv: Path, plan_zip: Path) -> Session:
    from app.services.importer import run_import

    run_import(db, library_path=library_csv, plan_path=plan_zip, media_dir=data_dir / "media")
    return db


@pytest.fixture
def client(seeded: Session) -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app, headers={"X-Profile-Id": str(TREY)}) as c:
        yield c
