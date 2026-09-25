from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Appearance
from app.services.calendar import CalendarService
from app.services.events import EventService

router = APIRouter(tags=["calendar"])
calendar_service = CalendarService()


def _load_event(session: Session, event_id: int):
    event = EventService(session).get_event_detail(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="イベントが見つかりません")
    return event


def _load_appearance(event, appearance_id: int) -> Appearance:
    appearance = next((item for item in event.appearances if item.id == appearance_id), None)
    if appearance is None:
        raise HTTPException(status_code=404, detail="出演情報が見つかりません")
    return appearance


def _ics_response(content: str, filename: str) -> Response:
    return Response(
        content=content,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/events/{event_id}/calendar/google/event", name="google_event_calendar")
def google_event_calendar(event_id: int, session: Session = Depends(get_session)):
    event = _load_event(session, event_id)
    return RedirectResponse(calendar_service.build_event_calendar_url(event), status_code=307)


@router.get("/events/{event_id}/calendar/google/appearance/{appearance_id}", name="google_appearance_calendar")
def google_appearance_calendar(event_id: int, appearance_id: int, session: Session = Depends(get_session)):
    event = _load_event(session, event_id)
    appearance = _load_appearance(event, appearance_id)
    url = calendar_service.build_appearance_calendar_url(event, appearance)
    if url is None:
        raise HTTPException(status_code=404, detail="出演時間が登録されていません")
    return RedirectResponse(url, status_code=307)


@router.get("/events/{event_id}/calendar/google/benefit/{appearance_id}", name="google_benefit_calendar")
def google_benefit_calendar(event_id: int, appearance_id: int, session: Session = Depends(get_session)):
    event = _load_event(session, event_id)
    appearance = _load_appearance(event, appearance_id)
    url = calendar_service.build_benefit_calendar_url(event, appearance)
    if url is None:
        raise HTTPException(status_code=404, detail="特典会時間が登録されていません")
    return RedirectResponse(url, status_code=307)


@router.get("/events/{event_id}/calendar/event.ics", name="event_calendar_ics")
def event_calendar_ics(event_id: int, session: Session = Depends(get_session)):
    event = _load_event(session, event_id)
    return _ics_response(calendar_service.build_event_ics(event), f"event-{event.id}.ics")


@router.get("/events/{event_id}/calendar/appearance/{appearance_id}.ics", name="appearance_calendar_ics")
def appearance_calendar_ics(event_id: int, appearance_id: int, session: Session = Depends(get_session)):
    event = _load_event(session, event_id)
    appearance = _load_appearance(event, appearance_id)
    content = calendar_service.build_appearance_ics(event, appearance)
    if content is None:
        raise HTTPException(status_code=404, detail="出演時間が登録されていません")
    return _ics_response(content, f"appearance-{appearance.id}.ics")


@router.get("/events/{event_id}/calendar/benefit/{appearance_id}.ics", name="benefit_calendar_ics")
def benefit_calendar_ics(event_id: int, appearance_id: int, session: Session = Depends(get_session)):
    event = _load_event(session, event_id)
    appearance = _load_appearance(event, appearance_id)
    content = calendar_service.build_benefit_ics(event, appearance)
    if content is None:
        raise HTTPException(status_code=404, detail="特典会時間が登録されていません")
    return _ics_response(content, f"benefit-{appearance.id}.ics")
