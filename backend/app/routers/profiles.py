from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app import schemas
from app.deps import DB
from app.models import Profile

router = APIRouter(prefix="/api/profiles", tags=["profiles"])


@router.get("", response_model=list[schemas.ProfileOut])
def list_profiles(db: DB) -> list[Profile]:
    return list(db.scalars(select(Profile).order_by(Profile.id)))


@router.patch("/{profile_id}", response_model=schemas.ProfileOut)
def update_profile(profile_id: int, body: schemas.ProfileUpdate, db: DB) -> Profile:
    profile = db.get(Profile, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Profile not found")
    if "email" in body.model_fields_set:
        profile.email = (body.email or "").strip() or None
    db.commit()
    return profile
