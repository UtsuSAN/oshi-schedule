from calendar import monthrange
from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.admin import router as admin_router
from app.calendar_routes import router as calendar_router
from app.imports import router as import_router
from app.db import get_session
from app.services.events import EventService, as_japan_datetime, japan_today

app = FastAPI(title="推し活スケジュール管理ツール")
app.include_router(admin_router)
app.include_router(import_router)
app.include_router(calendar_router)
APP_DIR = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=APP_DIR / "templates")
WEEKDAYS_JA = ("月", "火", "水", "木", "金", "土", "日")


def _format_jst(value, fmt: str) -> str:
    localized = as_japan_datetime(value)
    return localized.strftime(fmt) if localized else ""


templates.env.filters["jst"] = _format_jst


def _base_context(request: Request, session: Session, artist_id: int | None) -> dict:
    return {
        "request": request,
        "artists": EventService(session).get_artists(),
        "artist_id": artist_id,
        "filter_query": f"?artist_id={artist_id}" if artist_id is not None else "",
        "today": japan_today(),
        "weekdays": WEEKDAYS_JA,
    }


def _render(request: Request, name: str, context: dict) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name=name, context=context)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Small startup/readiness endpoint for the Increment 1 foundation."""
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse, name="today")
@app.get("/today", response_class=HTMLResponse, include_in_schema=False)
def today_page(
    request: Request,
    artist_id: int | None = Query(default=None, gt=0),
    session: Session = Depends(get_session),
):
    day = japan_today()
    context = _base_context(request, session, artist_id)
    context.update({"active_view": "today", "day": day, "events": EventService(session).get_today_events(day, artist_id)})
    return _render(request, "today.html", context)


@app.get("/week", response_class=HTMLResponse, name="week")
def week_page(
    request: Request,
    artist_id: int | None = Query(default=None, gt=0),
    session: Session = Depends(get_session),
):
    day = japan_today()
    monday = day - timedelta(days=day.weekday())
    event_list = EventService(session).get_week_events(day, artist_id)
    by_day: dict[date, list] = {monday + timedelta(days=i): [] for i in range(7)}
    for event in event_list:
        by_day[event.event_date].append(event)
    context = _base_context(request, session, artist_id)
    context.update({"active_view": "week", "week_start": monday, "week_end": monday + timedelta(days=6), "days": by_day})
    return _render(request, "week.html", context)


@app.get("/month", response_class=HTMLResponse, name="month")
def month_page(
    request: Request,
    year: int | None = Query(default=None, ge=1, le=9999),
    month: int | None = Query(default=None, ge=1, le=12),
    artist_id: int | None = Query(default=None, gt=0),
    session: Session = Depends(get_session),
):
    current = japan_today()
    year, month = year or current.year, month or current.month
    first = date(year, month, 1)
    last_day = monthrange(year, month)[1]
    events = EventService(session).get_month_events(year, month, artist_id)
    events_by_day: dict[date, list] = {}
    for event in events:
        events_by_day.setdefault(event.event_date, []).append(event)
    cells: list[dict] = [{"date": None, "events": []} for _ in range(first.weekday())]
    cells.extend({"date": date(year, month, day), "events": events_by_day.get(date(year, month, day), [])} for day in range(1, last_day + 1))
    cells.extend({"date": None, "events": []} for _ in range((-len(cells)) % 7))
    prev_month = first - timedelta(days=1) if first > date.min else None
    next_month = None
    if year < 9999 or month < 12:
        next_year = year + 1 if month == 12 else year
        next_month = date(next_year, 1 if month == 12 else month + 1, 1)
    context = _base_context(request, session, artist_id)
    context.update({"active_view": "month", "month_label": f"{year}年{month}月", "cells": cells,
                    "prev_month": prev_month, "next_month": next_month})
    return _render(request, "month.html", context)


@app.get("/day/{day}", response_class=HTMLResponse, name="day")
def day_page(
    day: date,
    request: Request,
    artist_id: int | None = Query(default=None, gt=0),
    session: Session = Depends(get_session),
):
    context = _base_context(request, session, artist_id)
    context.update({"active_view": "month", "day": day, "events": EventService(session).get_today_events(day, artist_id)})
    return _render(request, "day.html", context)


@app.get("/events/{event_id}", response_class=HTMLResponse, name="event_detail")
def event_detail(
    event_id: int,
    request: Request,
    artist_id: int | None = Query(default=None, gt=0),
    session: Session = Depends(get_session),
):
    service = EventService(session)
    event = service.get_event_detail(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="イベントが見つかりません")
    context = _base_context(request, session, artist_id)
    context.update({"event": event, "updated_at_jst": as_japan_datetime(event.updated_at)})
    return _render(request, "event_detail.html", context)
