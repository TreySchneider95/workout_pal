"""Request dependencies shared by the routers."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Profile

DB = Annotated[Session, Depends(get_db)]


def get_profile(
    db: DB,
    x_profile_id: Annotated[int | None, Header(description="Whose plan and history to use")] = None,
) -> Profile:
    """The person the request is for. Plans, sessions and settings are scoped to them."""
    if x_profile_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Choose a profile (X-Profile-Id header)")
    profile = db.get(Profile, x_profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Profile {x_profile_id} not found")
    return profile


CurrentProfile = Annotated[Profile, Depends(get_profile)]
