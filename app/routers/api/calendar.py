import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response
from icalendar import Calendar, Event
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import get_current_user, get_db

router = APIRouter()


def _get_event_or_404(event_id: int, db: Session) -> models.CalendarEvent:
    event = db.query(models.CalendarEvent).filter(models.CalendarEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


def _is_participant(event: models.CalendarEvent, user_id: int) -> bool:
    return any(p.user_id == user_id for p in event.participants)


def _rebuild_participants(event: models.CalendarEvent, participant_ids: list[int], creator_id: int, db: Session):
    db.query(models.CalendarEventParticipant).filter(
        models.CalendarEventParticipant.event_id == event.id
    ).delete()
    seen = set()
    all_ids = list(dict.fromkeys([creator_id] + participant_ids))
    for uid in all_ids:
        if uid in seen:
            continue
        seen.add(uid)
        if not db.query(models.User).filter(models.User.id == uid).first():
            raise HTTPException(status_code=400, detail=f"User {uid} not found")
        db.add(models.CalendarEventParticipant(event_id=event.id, user_id=uid))


@router.get("/my-feed-url")
def get_my_feed_url(
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if not current_user.ical_token:
        current_user.ical_token = str(uuid.uuid4())
        db.commit()
        db.refresh(current_user)
    base = str(request.base_url).rstrip("/")
    return {"url": f"{base}/api/calendar/feed/{current_user.ical_token}.ics"}


@router.get("/feed/{token}.ics", include_in_schema=False)
def get_ical_feed(token: str, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.ical_token == token).first()
    if not user:
        raise HTTPException(status_code=404, detail="Feed not found")

    events = (
        db.query(models.CalendarEvent)
        .join(models.CalendarEventParticipant)
        .filter(models.CalendarEventParticipant.user_id == user.id)
        .all()
    )

    cal = Calendar()
    cal.add("prodid", "-//Flat Expenses//Calendar//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", f"Flat Calendar – {user.name}")

    for ev in events:
        ical_ev = Event()
        ical_ev.add("uid", f"flat-event-{ev.id}@homeserver")
        ical_ev.add("summary", ev.title)
        if ev.description:
            ical_ev.add("description", ev.description)
        ical_ev.add("dtstart", ev.start_dt.replace(tzinfo=timezone.utc) if ev.start_dt.tzinfo is None else ev.start_dt)
        end = ev.end_dt or ev.start_dt
        ical_ev.add("dtend", end.replace(tzinfo=timezone.utc) if end.tzinfo is None else end)
        ical_ev.add("dtstamp", datetime.now(timezone.utc))
        cal.add_component(ical_ev)

    return Response(content=cal.to_ical(), media_type="text/calendar; charset=utf-8")


@router.get("/", response_model=list[schemas.CalendarEventRead])
def list_events(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.CalendarEvent)
    if not current_user.is_admin:
        query = (
            query.join(models.CalendarEventParticipant)
            .filter(models.CalendarEventParticipant.user_id == current_user.id)
        )
    return query.all()


@router.post("/", response_model=schemas.CalendarEventRead, status_code=status.HTTP_201_CREATED)
def create_event(
    payload: schemas.CalendarEventCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    event = models.CalendarEvent(
        title=payload.title,
        description=payload.description,
        start_dt=payload.start_dt,
        end_dt=payload.end_dt,
        creator_id=current_user.id,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    _rebuild_participants(event, payload.participant_ids, current_user.id, db)
    db.commit()
    db.refresh(event)
    return event


@router.get("/{event_id}", response_model=schemas.CalendarEventRead)
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    event = _get_event_or_404(event_id, db)
    if not current_user.is_admin and not _is_participant(event, current_user.id):
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.patch("/{event_id}", response_model=schemas.CalendarEventRead)
def update_event(
    event_id: int,
    payload: schemas.CalendarEventUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    event = _get_event_or_404(event_id, db)
    if not current_user.is_admin and event.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    for field in ("title", "description", "start_dt", "end_dt"):
        value = getattr(payload, field)
        if value is not None:
            setattr(event, field, value)

    if payload.participant_ids is not None:
        _rebuild_participants(event, payload.participant_ids, event.creator_id, db)

    db.commit()
    db.refresh(event)
    return event


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(
    event_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    event = _get_event_or_404(event_id, db)
    if not current_user.is_admin and event.creator_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    db.delete(event)
    db.commit()
    return None
