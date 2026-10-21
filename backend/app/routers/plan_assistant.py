"""Change a plan with outside help: build a prompt for an AI, then preview and apply its answer."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app import schemas
from app.config import get_settings
from app.deps import DB, CurrentProfile
from app.models import PlanRevision, Profile
from app.services import plan_exchange
from app.services.mailer import EmailError, send_email

router = APIRouter(prefix="/api/plan-assistant", tags=["plan assistant"])

OnDate = Annotated[date | None, Query(alias="date", description="The device's local date")]


def _preview(db: DB, profile: Profile, text: str) -> tuple[schemas.PlanPreview, plan_exchange.ValidatedPlan | None]:
    try:
        doc = plan_exchange.read_document(text)
    except plan_exchange.DocumentError as exc:
        return schemas.PlanPreview(ok=False, summary=None, errors=exc.errors, warnings=[], workouts=[]), None
    plan = plan_exchange.validate_document(db, doc)
    workouts = []
    if plan.ok:
        proposed = plan_exchange.plan_to_document(plan)
        workouts = plan_exchange.diff_plans(plan_exchange.export_plan(db, profile.id), proposed)
    return schemas.PlanPreview(ok=plan.ok, summary=plan.summary, errors=plan.errors,
                               warnings=plan.warnings, workouts=workouts), plan


def _email_body(profile: Profile, request: str) -> str:
    app_url = get_settings().app_url
    back = f"{app_url.rstrip('/')}/schedule/assistant" if app_url else "Workout Pal → Plan → Change with AI"
    return f"""Hi {profile.name},

Here's the prompt for changing your workout plan. You asked for:

    {request.strip()}

1. Open the attached workout-pal-prompt.txt, copy all of it and paste it into ChatGPT,
   Claude or Gemini.
2. Answer any questions it asks.
3. When it gives you a JSON block, copy the AI's reply and paste it into:
   {back}
   You'll see exactly what changes before anything is saved, and you can undo it later.

The full prompt is also below.

----------------------------------------------------------------------

"""


@router.get("/status", response_model=schemas.AssistantStatus)
def assistant_status(profile: CurrentProfile) -> schemas.AssistantStatus:
    return schemas.AssistantStatus(email_enabled=get_settings().email_enabled, email=profile.email)


@router.post("/prompt", response_model=schemas.PromptOut)
def create_prompt(body: schemas.PromptRequest, db: DB, profile: CurrentProfile, on_date: OnDate = None) -> schemas.PromptOut:
    prompt = plan_exchange.build_prompt(db, profile, body.request, on_date)
    db.commit()  # settings row may have been created
    return schemas.PromptOut(prompt=prompt)


@router.post("/email", response_model=schemas.EmailSent)
def email_prompt(body: schemas.PromptRequest, db: DB, profile: CurrentProfile, on_date: OnDate = None) -> schemas.EmailSent:
    if not profile.email:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"Add an email address for {profile.name} in Settings")
    prompt = plan_exchange.build_prompt(db, profile, body.request, on_date)
    db.commit()
    try:
        send_email(profile.email, "Your Workout Pal plan prompt", _email_body(profile, body.request) + prompt,
                   [("workout-pal-prompt.txt", prompt)])
    except EmailError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return schemas.EmailSent(sent_to=profile.email)


@router.get("/export")
def export_plan(db: DB, profile: CurrentProfile) -> dict:
    """The current plan as a plan document (also a handy backup)."""
    return plan_exchange.export_plan(db, profile.id)


@router.post("/preview", response_model=schemas.PlanPreview)
def preview(body: schemas.PlanDocumentIn, db: DB, profile: CurrentProfile) -> schemas.PlanPreview:
    return _preview(db, profile, body.document)[0]


@router.post("/apply", response_model=schemas.PlanRevisionOut)
def apply(body: schemas.PlanDocumentIn, db: DB, profile: CurrentProfile) -> schemas.PlanRevisionOut:
    result, plan = _preview(db, profile, body.document)
    if plan is None or not plan.ok:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, {"message": result.errors[0], "errors": result.errors})
    revision = plan_exchange.apply_plan(db, profile.id, plan)
    return schemas.PlanRevisionOut.model_validate(revision).model_copy(update={"can_undo": True})


@router.get("/revisions", response_model=list[schemas.PlanRevisionOut])
def list_revisions(db: DB, profile: CurrentProfile) -> list[schemas.PlanRevisionOut]:
    revisions = db.scalars(
        select(PlanRevision).where(PlanRevision.profile_id == profile.id)
        .order_by(PlanRevision.created_at.desc(), PlanRevision.id.desc()).limit(20)
    ).all()
    return [
        schemas.PlanRevisionOut.model_validate(r).model_copy(update={"can_undo": i == 0})
        for i, r in enumerate(revisions)
    ]


@router.post("/revisions/{revision_id}/undo", response_model=schemas.PlanRevisionOut)
def undo(revision_id: int, db: DB, profile: CurrentProfile) -> schemas.PlanRevisionOut:
    latest = plan_exchange.latest_revision(db, profile.id)
    if latest is None or latest.id != revision_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only the most recent change can be undone")
    try:
        revision = plan_exchange.undo_revision(db, latest)
    except plan_exchange.DocumentError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT,
                            {"message": "The previous plan can't be restored: " + exc.errors[0], "errors": exc.errors}) from exc
    return schemas.PlanRevisionOut.model_validate(revision).model_copy(update={"can_undo": True})
